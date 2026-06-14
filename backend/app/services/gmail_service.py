import base64
from email.message import EmailMessage
import mimetypes
from typing import Any

import httpx

from app.schemas.gmail import (
    GmailDraftRequest,
    GmailDraftResponse,
    GmailRecentEmail,
    GmailRecentEmailsResponse,
    GmailSendRequest,
    GmailSendResponse,
    GmailStatusResponse,
    GmailTestResponse,
)
from app.services.connector_registry_service import connector_registry_service
from app.services.file_index_service import file_index_service
from app.services.gmail_credentials_store import GmailCredentialsError, gmail_credentials_store
from app.services.gmail_oauth_service import GmailOAuthError, gmail_oauth_service
from app.services.gmail_token_store import gmail_token_store


GMAIL_API_BASE_URL = "https://gmail.googleapis.com/gmail/v1"
GMAIL_ATTACHMENT_MAX_TOTAL_BYTES = 20 * 1024 * 1024
GMAIL_BLOCKED_ATTACHMENT_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".db",
    ".dll",
    ".env",
    ".exe",
    ".key",
    ".pem",
    ".ps1",
    ".rar",
    ".sh",
    ".sqlite",
    ".zip",
    ".7z",
}


class GmailConnectorError(ValueError):
    pass


GmailAttachmentPayload = dict[str, Any]


class GmailService:
    def status(self) -> GmailStatusResponse:
        state = gmail_credentials_store.load_state()
        credentials_configured = gmail_credentials_store.credentials_exist()
        token = gmail_token_store.load_token()
        connected = bool(credentials_configured and token and state.get("connected"))
        scopes = list(state.get("scopes") or (token.get("scopes") if token else []) or [])
        return GmailStatusResponse(
            credentials_configured=credentials_configured,
            connected=connected,
            reconnect_required=bool(state.get("reconnect_required")),
            status="connected" if connected else "configured" if credentials_configured else "needs_configuration",
            email_address=state.get("email_address"),
            scopes=scopes,
            last_error=state.get("last_error"),
            connected_at=state.get("connected_at"),
            credential_file_name=state.get("credential_file_name"),
            capabilities={
                "read_email": connected,
                "search_email": connected,
                "create_draft": connected and "https://www.googleapis.com/auth/gmail.compose" in scopes,
                "send_email": connected and "https://www.googleapis.com/auth/gmail.compose" in scopes,
                "attachments": connected and "https://www.googleapis.com/auth/gmail.compose" in scopes,
                "max_attachment_total_mb": 20,
            },
        )

    def upload_credentials(self, filename: str, content: str) -> GmailStatusResponse:
        try:
            gmail_credentials_store.save_uploaded_credentials(filename, content)
        except GmailCredentialsError as error:
            raise GmailConnectorError(str(error)) from error
        connector_registry_service.save_config("gmail", {"credentials_configured": True, "credential_file_name": filename})
        connector_registry_service.set_enabled("gmail", False)
        connector_registry_service.record_seen("gmail", {"connected": False, "last_error": None})
        return self.status()

    def start_connect(self) -> str:
        try:
            auth_url = gmail_oauth_service.start_oauth()
        except (GmailCredentialsError, GmailOAuthError) as error:
            raise GmailConnectorError(str(error)) from error
        connector_registry_service.set_enabled("gmail", True)
        connector_registry_service.record_seen("gmail", {"connected": False, "last_error": None})
        return auth_url

    def complete_oauth_callback(self, code: str | None, state: str | None, error: str | None = None) -> GmailStatusResponse:
        try:
            gmail_oauth_service.handle_callback(code, state, error)
            profile = self.get_profile()
        except (GmailOAuthError, GmailCredentialsError, GmailConnectorError) as service_error:
            connector_registry_service.record_seen("gmail", {"connected": False, "last_error": str(service_error)})
            raise GmailConnectorError(str(service_error)) from service_error
        current_state = gmail_credentials_store.load_state()
        current_state.update({"email_address": profile.get("emailAddress"), "connected": True, "last_error": None})
        gmail_credentials_store.save_state(current_state)
        connector_registry_service.record_seen(
            "gmail",
            {
                "connected": True,
                "email_address": profile.get("emailAddress"),
                "connected_at": current_state.get("connected_at"),
                "last_error": None,
            },
        )
        return self.status()

    def test_connection(self) -> GmailTestResponse:
        profile = self.get_profile()
        email = str(profile.get("emailAddress") or "")
        state = gmail_credentials_store.load_state()
        state.update({"email_address": email, "connected": True, "last_error": None, "reconnect_required": False})
        gmail_credentials_store.save_state(state)
        connector_registry_service.record_seen("gmail", {"connected": True, "email_address": email, "last_error": None})
        return GmailTestResponse(
            status="connected",
            connected=True,
            email_address=email,
            message=f"Connected to Gmail as {email}.",
        )

    def get_profile(self) -> dict[str, Any]:
        return self._request("GET", "/users/me/profile")

    def list_recent_emails(self, limit: int = 5) -> GmailRecentEmailsResponse:
        safe_limit = max(1, min(25, int(limit or 5)))
        data = self._request("GET", "/users/me/messages", params={"maxResults": safe_limit, "labelIds": "INBOX"})
        emails: list[GmailRecentEmail] = []
        for item in data.get("messages") if isinstance(data.get("messages"), list) else []:
            message_id = str(item.get("id") or "")
            if not message_id:
                continue
            detail = self._request(
                "GET",
                f"/users/me/messages/{message_id}",
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            headers = _headers_to_dict(((detail.get("payload") or {}).get("headers") or []))
            emails.append(
                GmailRecentEmail(
                    id=message_id,
                    thread_id=detail.get("threadId"),
                    subject=headers.get("subject", ""),
                    from_address=headers.get("from", ""),
                    date=headers.get("date"),
                    snippet=str(detail.get("snippet") or ""),
                )
            )
        return GmailRecentEmailsResponse(emails=emails, total=len(emails))

    def create_draft(self, request: GmailDraftRequest) -> GmailDraftResponse:
        indexed_attachments = self.read_indexed_attachments(request.indexed_attachments)
        if indexed_attachments:
            return self.create_draft_with_attachments(
                to=[request.to],
                subject=request.subject,
                body=request.body,
                cc=request.cc,
                bcc=request.bcc,
                attachments=indexed_attachments,
            )
        raw = self._build_raw_message([request.to], request.subject, request.body, cc=request.cc, bcc=request.bcc)
        return self._create_draft_from_raw(raw)

    def create_draft_with_attachments(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[GmailAttachmentPayload] | None = None,
    ) -> GmailDraftResponse:
        self._validate_message_fields(to, subject, body)
        safe_attachments = self.validate_attachments(attachments or [])
        raw = self._build_raw_message(to, subject, body, cc=cc, bcc=bcc, attachments=safe_attachments)
        return self._create_draft_from_raw(raw)

    def _create_draft_from_raw(self, raw: str) -> GmailDraftResponse:
        data = self._request("POST", "/users/me/drafts", json={"message": {"raw": raw}})
        draft_id = str(data.get("id") or "")
        message_id = str((data.get("message") or {}).get("id") or "") or None
        if not draft_id:
            raise GmailConnectorError("Draft creation failed.")
        return GmailDraftResponse(
            status="created",
            draft_id=draft_id,
            message_id=message_id,
            message="Draft created in Gmail. It was not sent.",
        )

    def send_message(self, request: GmailSendRequest) -> GmailSendResponse:
        if request.confirmation is not True:
            raise GmailConnectorError("Gmail send requires confirmation.")
        status = self.status()
        if not status.connected:
            raise GmailConnectorError("Gmail is not connected.")
        if not status.capabilities.get("send_email"):
            raise GmailConnectorError("Gmail send is not connected yet. You can create a draft instead.")
        indexed_attachments = self.read_indexed_attachments(request.indexed_attachments)
        if indexed_attachments:
            return self.send_message_with_attachments(
                to=request.to,
                subject=request.subject,
                body=request.body,
                confirmation=request.confirmation,
                cc=request.cc,
                bcc=request.bcc,
                attachments=indexed_attachments,
            )
        raw = self._build_raw_message(request.to, request.subject, request.body, cc=request.cc, bcc=request.bcc)
        return self._send_raw_message(raw)

    def send_message_with_attachments(
        self,
        to: list[str],
        subject: str,
        body: str,
        confirmation: bool,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[GmailAttachmentPayload] | None = None,
    ) -> GmailSendResponse:
        if confirmation is not True:
            raise GmailConnectorError("Gmail send requires confirmation.")
        status = self.status()
        if not status.connected:
            raise GmailConnectorError("Gmail is not connected.")
        if not status.capabilities.get("send_email"):
            raise GmailConnectorError("Gmail send is not connected yet. You can create a draft instead.")
        self._validate_message_fields(to, subject, body)
        safe_attachments = self.validate_attachments(attachments or [])
        raw = self._build_raw_message(to, subject, body, cc=cc, bcc=bcc, attachments=safe_attachments)
        return self._send_raw_message(raw)

    def _send_raw_message(self, raw: str) -> GmailSendResponse:
        data = self._request("POST", "/users/me/messages/send", json={"raw": raw})
        message_id = str(data.get("id") or "") or None
        thread_id = str(data.get("threadId") or "") or None
        return GmailSendResponse(
            status="sent",
            message_id=message_id,
            thread_id=thread_id,
            message="Email sent from Gmail.",
        )

    def create_test_draft(self) -> GmailDraftResponse:
        profile = self.get_profile()
        email_address = str(profile.get("emailAddress") or "")
        if not email_address:
            raise GmailConnectorError("Could not read connected Gmail address.")
        return self.create_draft(
            GmailDraftRequest(
                to=email_address,
                subject="MindOS Gmail test draft",
                body="This is a test draft created by MindOS.",
            )
        )

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        if not draft_id.strip():
            raise GmailConnectorError("Draft id is required.")
        return self._request("POST", f"/users/me/drafts/{draft_id.strip()}/send")

    def validate_attachments(self, attachments: list[GmailAttachmentPayload]) -> list[GmailAttachmentPayload]:
        total_size = 0
        safe_attachments: list[GmailAttachmentPayload] = []
        for attachment in attachments:
            filename = str(attachment.get("filename") or "").strip()
            if not filename:
                raise GmailConnectorError("Attachment filename is required.")
            extension = _extension_for_filename(filename)
            if extension in GMAIL_BLOCKED_ATTACHMENT_EXTENSIONS:
                raise GmailConnectorError(f"Remove blocked file type: {filename}.")
            content = attachment.get("content")
            if not isinstance(content, bytes):
                raise GmailConnectorError(f"Could not read attachment: {filename}.")
            size = int(attachment.get("size") or len(content))
            total_size += size
            if total_size > GMAIL_ATTACHMENT_MAX_TOTAL_BYTES:
                raise GmailConnectorError("Attachment total size is too large. Keep attachments under 20 MB.")
            safe_attachments.append({**attachment, "filename": filename, "content": content, "size": size})
        return safe_attachments

    def read_indexed_attachments(self, references: list[Any] | None) -> list[GmailAttachmentPayload]:
        if not references:
            return []
        try:
            return file_index_service.read_indexed_attachments(list(references))
        except ValueError as error:
            raise GmailConnectorError(str(error)) from error

    def disconnect(self) -> GmailStatusResponse:
        gmail_oauth_service.disconnect()
        connector_registry_service.set_enabled("gmail", False)
        connector_registry_service.record_seen("gmail", {"connected": False, "last_error": None})
        return self.status()

    def remove_credentials(self) -> GmailStatusResponse:
        gmail_oauth_service.remove_credentials()
        connector_registry_service.save_config("gmail", {})
        connector_registry_service.set_enabled("gmail", False)
        connector_registry_service.record_seen("gmail", {"connected": False, "last_error": None})
        return self.status()

    def get_agent_tool_status(self) -> str:
        current = self.status()
        if not current.credentials_configured:
            return "Please upload Google OAuth credentials.json first."
        if not current.connected:
            return "Gmail is not connected. Please connect Gmail from Settings -> Connectors -> Gmail."
        if current.reconnect_required:
            return "Gmail connection expired. Please reconnect."
        return f"Gmail connected as {current.email_address or 'the selected account'}."

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            access_token = gmail_oauth_service.ensure_access_token()
        except GmailOAuthError as error:
            raise GmailConnectorError(str(error)) from error
        url = f"{GMAIL_API_BASE_URL}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
                **kwargs,
            )
        except httpx.RequestError as error:
            raise GmailConnectorError("Network error while contacting Gmail.") from error
        if response.status_code == 401:
            gmail_oauth_service.disconnect()
            raise GmailConnectorError("Token expired or revoked; please reconnect.")
        if response.status_code == 403:
            raise GmailConnectorError("Gmail API is not enabled or the account lacks permission.")
        if response.status_code >= 400:
            raise GmailConnectorError("Gmail request failed.")
        value = response.json() if response.content else {}
        return value if isinstance(value, dict) else {}

    def _validate_message_fields(self, to: list[str], subject: str, body: str) -> None:
        if not [item.strip() for item in to if item.strip()]:
            raise GmailConnectorError("Add a recipient before sending.")
        if not subject.strip():
            raise GmailConnectorError("Add a subject before sending.")
        if not body.strip():
            raise GmailConnectorError("Add an email body before sending.")

    def _build_raw_message(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[GmailAttachmentPayload] | None = None,
    ) -> str:
        message = EmailMessage()
        message["To"] = ", ".join([item.strip() for item in to if item.strip()])
        if cc:
            message["Cc"] = ", ".join([item.strip() for item in cc if item.strip()])
        if bcc:
            message["Bcc"] = ", ".join([item.strip() for item in bcc if item.strip()])
        message["Subject"] = subject
        message.set_content(body)
        for attachment in attachments or []:
            filename = str(attachment.get("filename") or "attachment")
            content_type = str(attachment.get("content_type") or "") or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
            maintype, _, subtype = content_type.partition("/")
            message.add_attachment(
                attachment["content"],
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=filename,
            )
        return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


def _headers_to_dict(headers: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for header in headers:
        name = str(header.get("name") or "").lower()
        if name:
            result[name] = str(header.get("value") or "")
    return result


def _extension_for_filename(filename: str) -> str:
    if "." not in filename:
        return ""
    return f".{filename.rsplit('.', 1)[-1].lower()}"


gmail_service = GmailService()
