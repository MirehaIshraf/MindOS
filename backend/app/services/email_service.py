import email as email_lib
import email.header
import email.policy
import hashlib
import imaplib
import re
import socket
import ssl
from datetime import datetime, timezone
from typing import Any

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.repositories.base import EventRepository
from app.schemas.email import (
    EmailAttachment,
    EmailConfigRequest,
    EmailFolder,
    EmailFoldersResponse,
    EmailStatusResponse,
    EmailSyncRequest,
    EmailSyncResponse,
    EmailTestResponse,
)
from app.services.connector_registry_service import connector_registry_service
from app.services.relationship_service import relationship_service

EXCERPT_MAX_CHARS = 1000
BODY_FETCH_MAX_BYTES = 32768


class EmailConnectorError(ValueError):
    pass


class EmailService:
    def __init__(self, events: EventRepository | None = None) -> None:
        self._events = events or get_event_repository()

    def status(self) -> EmailStatusResponse:
        config = self._config()
        enabled = connector_registry_service.is_enabled("email")
        heartbeat = connector_registry_service.heartbeat_metadata("email")
        event_count = len([e for e in self._events.list_all_events(include_hidden=True) if e.source.value == "email"])
        configured = bool(config.get("password"))
        connected = bool(enabled and configured and heartbeat.get("account_email"))
        return EmailStatusResponse(
            enabled=enabled,
            configured=configured,
            connected=connected,
            status=connector_registry_service.get_connector("email").status,
            provider=str(config.get("provider") or "imap"),
            account_email=str(heartbeat.get("account_email") or config.get("email_address") or "") or None,
            last_sync_at=str(heartbeat.get("last_sync_at") or "") or None,
            last_error=str(heartbeat.get("last_error") or "") or None,
            selected_scope=str(config.get("sync_scope") or "recent"),
            event_count=event_count,
            has_credentials=configured,
        )

    def save_config(self, request: EmailConfigRequest) -> EmailStatusResponse:
        current = self._config()
        next_config: dict[str, Any] = {
            **current,
            "provider": request.provider,
            "imap_host": (request.imap_host or "imap.gmail.com").strip(),
            "imap_port": request.imap_port,
            "imap_ssl": request.imap_ssl,
            "sync_scope": request.sync_scope,
            "folder_name": (request.folder_name or "INBOX").strip(),
            "max_items": request.max_items,
        }
        if request.email_address is not None:
            next_config["email_address"] = request.email_address.strip()
        if request.username is not None:
            next_config["username"] = request.username.strip()
        password = (request.password or "").strip()
        if password:
            next_config["password"] = password
        elif request.password is not None:
            next_config.pop("password", None)
            connector_registry_service.set_enabled("email", False)
        connector_registry_service.save_config("email", next_config)
        heartbeat_update: dict[str, Any] = {"last_error": None}
        if request.password is not None and not password:
            heartbeat_update["account_email"] = None
        connector_registry_service.record_seen("email", heartbeat_update)
        return self.status()

    def test_connection(self) -> EmailTestResponse:
        config = self._config()
        conn = self._connect(config)
        try:
            account_email = str(config.get("email_address") or config.get("username") or "")
            conn.logout()
        except Exception:
            pass
        connector_registry_service.record_seen("email", {"account_email": account_email, "last_error": None})
        return EmailTestResponse(
            status="connected",
            connected=True,
            account_email=account_email or None,
            message=f"Connected to {config.get('imap_host')} as {account_email}.",
        )

    def list_folders(self) -> EmailFoldersResponse:
        self._require_configured()
        config = self._config()
        conn = self._connect(config)
        folders: list[EmailFolder] = []
        try:
            typ, folder_list = conn.list()
            if typ == "OK":
                for item in (folder_list or []):
                    name = _parse_folder_name(item)
                    if name:
                        display = name.split("/")[-1].split(".")[-1] or name
                        folders.append(EmailFolder(name=name, display_name=display))
        except Exception:
            pass
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return EmailFoldersResponse(folders=folders, total=len(folders))

    def sync(self, request: EmailSyncRequest) -> EmailSyncResponse:
        self._require_configured()
        config = self._config()
        conn = self._connect(config)

        imported = 0
        updated = 0
        skipped = 0
        failed = 0
        created_ids: list[str] = []
        warnings: list[str] = []
        account_email = str(config.get("email_address") or config.get("username") or "")

        try:
            folder = (request.folder_name or "INBOX").strip() or "INBOX"
            try:
                conn.select(folder, readonly=True)
            except Exception as exc:
                raise EmailConnectorError(f"Could not select folder '{folder}'.") from exc

            search_criteria = _scope_to_search(request.scope)
            typ, data = conn.search(None, search_criteria)
            if typ != "OK" or not data or not data[0]:
                return EmailSyncResponse(
                    status="success",
                    emails_seen=0,
                    imported_count=0,
                    updated_count=0,
                    skipped_count=0,
                    failed_count=0,
                    message="No matching emails found for this sync scope.",
                )

            msg_ids = data[0].split()
            msg_ids = msg_ids[-request.max_items:]

            for msg_id in reversed(msg_ids):
                try:
                    result = self._fetch_and_upsert(conn, msg_id, account_email, folder, request.include_body_excerpt)
                    if result["created"]:
                        imported += 1
                    else:
                        updated += 1
                    if result["event_id"]:
                        created_ids.append(result["event_id"])
                except EmailConnectorError as exc:
                    failed += 1
                    warnings.append(str(exc))
                except Exception as exc:
                    failed += 1
                    warnings.append(f"Failed to process message: {exc}")

        finally:
            try:
                conn.logout()
            except Exception:
                pass

        connector_registry_service.record_seen(
            "email",
            {
                "account_email": account_email,
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
                "last_error": warnings[0] if warnings else None,
            },
        )

        total_seen = len(msg_ids) if "msg_ids" in dir() else 0
        status = "partial" if failed else "success"
        return EmailSyncResponse(
            status=status,
            emails_seen=total_seen,
            imported_count=imported,
            updated_count=updated,
            skipped_count=skipped,
            failed_count=failed,
            events_created=created_ids,
            warnings=warnings,
            message=f"Synced {total_seen} emails. Imported {imported}, updated {updated}.",
        )

    def _fetch_and_upsert(
        self,
        conn: imaplib.IMAP4,
        msg_id: bytes,
        account_email: str,
        folder: str,
        include_body_excerpt: bool,
    ) -> dict[str, Any]:
        typ, msg_data = conn.fetch(msg_id, "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            raise EmailConnectorError("Failed to fetch message.")

        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else None
        if not raw:
            raise EmailConnectorError("Empty message data.")

        msg = email_lib.message_from_bytes(raw, policy=email_lib.policy.default)

        subject = _decode_header_value(msg.get("Subject") or "")
        sender = _decode_header_value(msg.get("From") or "")
        to_raw = _decode_header_value(msg.get("To") or "")
        to_list = [addr.strip() for addr in to_raw.split(",") if addr.strip()]
        date_str = _decode_header_value(msg.get("Date") or "")
        message_id = _decode_header_value(msg.get("Message-ID") or "").strip("<>").strip()

        dedupe_key = _make_dedupe_key(account_email, message_id, subject, sender, date_str)
        timestamp = _parse_email_date(date_str)

        attachments: list[dict[str, Any]] = []
        body_excerpt = ""

        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition.lower():
                filename = part.get_filename() or ""
                size = len(part.get_payload(decode=True) or b"")
                attachments.append({
                    "filename": _decode_header_value(filename),
                    "mime_type": content_type,
                    "size": size,
                })
            elif content_type == "text/plain" and not body_excerpt and include_body_excerpt:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="replace")
                        body_excerpt = _clean_text(text)[:EXCERPT_MAX_CHARS]
                except Exception:
                    pass

        content_lines = [
            f"From: {sender}",
            f"Date: {date_str}",
            f"Subject: {subject}",
        ]
        if body_excerpt:
            content_lines.append(f"Excerpt: {body_excerpt}")

        metadata: dict[str, Any] = {
            "provider": "imap",
            "account_email": account_email,
            "message_id": message_id,
            "from": sender,
            "to": to_list,
            "date": date_str,
            "folder": folder,
            "has_attachments": bool(attachments),
            "attachments": attachments,
            "dedupe_key": dedupe_key,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }

        title = f"Email: {subject}" if subject else "Email: (no subject)"
        content = "\n".join(content_lines)
        return self._upsert_event(title, content, metadata, timestamp)

    def _upsert_event(
        self,
        title: str,
        content: str,
        metadata: dict[str, Any],
        timestamp: datetime | None,
    ) -> dict[str, Any]:
        existing = self._events.find_event_by_metadata("email", "email_message", "dedupe_key", str(metadata["dedupe_key"]))
        if existing:
            merged = {**existing.metadata, **metadata}
            self._events.update_event_content_and_metadata(existing.id, content=content, metadata=merged, title=title, timestamp=timestamp)
            return {"created": False, "event_id": existing.id}
        payload: dict[str, Any] = {
            "source": EventSource.email,
            "type": "email_message",
            "title": title,
            "content": content,
            "metadata": metadata,
            "embedding_status": EmbeddingStatus.not_required,
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        event = self._events.create_event(payload)
        relationship_service.detect_relationships_for_event(event)
        return {"created": True, "event_id": event.id}

    def _connect(self, config: dict[str, Any]) -> imaplib.IMAP4:
        host = str(config.get("imap_host") or "imap.gmail.com").strip()
        port = int(config.get("imap_port") or 993)
        use_ssl = bool(config.get("imap_ssl", True))
        username = str(config.get("username") or config.get("email_address") or "").strip()
        password = str(config.get("password") or "").strip()

        if not username or not password:
            raise EmailConnectorError("Email credentials are not configured.")
        try:
            if use_ssl:
                conn = imaplib.IMAP4_SSL(host, port)
            else:
                conn = imaplib.IMAP4(host, port)
        except (OSError, socket.gaierror, ssl.SSLError) as exc:
            connector_registry_service.record_seen("email", {"last_error": "Could not connect to the mail server."})
            raise EmailConnectorError("Could not connect to the mail server. Check host, port, SSL, and credentials.") from exc
        try:
            conn.login(username, password)
        except imaplib.IMAP4.error as exc:
            connector_registry_service.record_seen("email", {"last_error": "Email credentials are invalid or expired."})
            raise EmailConnectorError("Email credentials are invalid or expired.") from exc
        return conn

    def _require_configured(self) -> None:
        config = self._config()
        if not config.get("password"):
            raise EmailConnectorError("Email connector is not configured.")

    def _config(self) -> dict[str, Any]:
        return connector_registry_service.get_config_dict("email")


def _scope_to_search(scope: str) -> str:
    if scope == "unread":
        return "UNSEEN"
    if scope == "starred":
        return "FLAGGED"
    return "ALL"


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded_parts: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return " ".join(decoded_parts).strip()


def _make_dedupe_key(account_email: str, message_id: str, subject: str, sender: str, date_str: str) -> str:
    if message_id:
        return f"{account_email}:{message_id}"
    raw = f"{account_email}:{subject}:{sender}:{date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _parse_email_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        return None


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_folder_name(item: bytes | str) -> str:
    if isinstance(item, bytes):
        item = item.decode("utf-8", errors="replace")
    match = re.search(r'"([^"]+)"\s*$', item) or re.search(r"(\S+)\s*$", item)
    if match:
        name = match.group(1).strip('"').strip()
        if name not in {"NIL", ""}:
            return name
    return ""


email_service = EmailService()
