import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.repositories.base import EventRepository
from app.schemas.email import (
    EmailCapabilityResponse,
    EmailConnectResponse,
    EmailDisconnectResponse,
    EmailDraftRequest,
    EmailDraftResponse,
    EmailMcpConfigRequest,
    EmailStatusResponse,
    EmailSyncRequest,
    EmailSyncResponse,
    EmailTestResponse,
    NormalizedEmailAttachment,
    NormalizedEmailMessage,
)
from app.services.connector_registry_service import connector_registry_service
from app.services.relationship_service import relationship_service

EXCERPT_MAX_CHARS = 1600
REQUEST_TIMEOUT_SECONDS = 30.0


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
        configured = self._is_configured(config)
        connected = bool(enabled and configured and heartbeat.get("connected"))
        capabilities = _capabilities_from_dict(dict(heartbeat.get("capabilities") or config.get("capabilities") or {}))
        return EmailStatusResponse(
            enabled=enabled,
            configured=configured,
            connected=connected,
            status=connector_registry_service.get_connector("email").status,
            provider_type="email_mcp",
            provider_name=str(config.get("provider_name") or "") or None,
            api_base_url=str(config.get("api_base_url") or "") or None,
            auth_type=str(config.get("auth_type") or "none"),
            auth_header_name=str(config.get("auth_header_name") or "Authorization"),
            account_label=str(config.get("account_label") or "") or None,
            last_sync_at=str(heartbeat.get("last_sync_at") or "") or None,
            last_error=str(heartbeat.get("last_error") or "") or None,
            selected_scope=str(config.get("sync_scope") or "recent"),
            event_count=event_count,
            has_api_key=bool(config.get("api_key")),
            capabilities=capabilities,
        )

    def save_config(self, request: EmailMcpConfigRequest) -> EmailStatusResponse:
        current = self._config()
        cleaned_url = request.api_base_url.strip().rstrip("/") if request.api_base_url.strip().lower() != "mock" else "mock"
        next_config: dict[str, Any] = {
            **current,
            "provider_type": "email_mcp",
            "provider_name": request.provider_name.strip(),
            "api_base_url": cleaned_url,
            "auth_type": request.auth_type,
            "auth_header_name": request.auth_header_name.strip() or "Authorization",
            "account_label": (request.account_label or "").strip(),
            "tool_mapping": request.tool_mapping.model_dump(),
        }
        if request.api_key is not None and request.api_key.strip():
            next_config["api_key"] = request.api_key.strip()
        elif request.api_key is not None and not request.api_key.strip():
            next_config.pop("api_key", None)
        connector_registry_service.save_config("email", next_config)
        connector_registry_service.record_seen("email", {"connected": False, "last_error": None, "capabilities": None})
        return self.status()

    def test_connection(self) -> EmailTestResponse:
        config = self._configured_config()
        capabilities = self._discover_capabilities(config)
        connector_registry_service.record_seen(
            "email",
            {
                "connected": True,
                "provider_name": config.get("provider_name"),
                "account_label": config.get("account_label"),
                "capabilities": capabilities.model_dump(),
                "last_error": None,
            },
        )
        return EmailTestResponse(
            status="connected",
            connected=True,
            provider_name=str(config.get("provider_name") or ""),
            account_label=str(config.get("account_label") or "") or None,
            capabilities=capabilities,
            message=f"Connected to {config.get('provider_name')}.",
        )

    def connect(self) -> EmailConnectResponse:
        config = self._configured_config()
        heartbeat = connector_registry_service.heartbeat_metadata("email")
        capabilities = _capabilities_from_dict(dict(heartbeat.get("capabilities") or {}))
        if not any([capabilities.search_emails, capabilities.read_email, capabilities.list_folders, capabilities.create_draft]):
            capabilities = self._discover_capabilities(config)
        connector_registry_service.set_enabled("email", True)
        connector_registry_service.record_seen(
            "email",
            {
                "connected": True,
                "provider_name": config.get("provider_name"),
                "account_label": config.get("account_label"),
                "capabilities": capabilities.model_dump(),
                "last_error": None,
            },
        )
        return EmailConnectResponse(status="connected", connected=True, message="Email connector connected.")

    def disconnect(self) -> EmailDisconnectResponse:
        connector_registry_service.set_enabled("email", False)
        connector_registry_service.record_seen("email", {"connected": False, "last_error": None})
        return EmailDisconnectResponse(status="disconnected", message="Email connector disconnected.")

    def capabilities(self) -> EmailCapabilityResponse:
        config = self._configured_config()
        capabilities = self._discover_capabilities(config)
        connector_registry_service.record_seen("email", {"capabilities": capabilities.model_dump(), "last_error": None})
        return capabilities

    def sync(self, request: EmailSyncRequest) -> EmailSyncResponse:
        self._require_connected()
        config = self._configured_config()
        messages = self.search_messages(config, request)
        imported = 0
        updated = 0
        failed = 0
        created_ids: list[str] = []
        warnings: list[str] = []

        for message in messages:
            try:
                result = self._upsert_email_message(config, message)
                imported += int(result["created"])
                updated += int(not result["created"])
                if result["event_id"]:
                    created_ids.append(result["event_id"])
            except Exception as exc:
                failed += 1
                warnings.append(f"Failed to process email {message.id}: {_safe_error(exc)}")

        connector_registry_service.save_config("email", {**config, "sync_scope": request.scope})
        connector_registry_service.record_seen(
            "email",
            {
                "connected": True,
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
                "last_error": warnings[0] if warnings else None,
            },
        )

        status = "partial" if failed else "success"
        return EmailSyncResponse(
            status=status,
            emails_seen=len(messages),
            imported_count=imported,
            updated_count=updated,
            skipped_count=0,
            failed_count=failed,
            events_created=created_ids,
            warnings=warnings,
            message=f"Synced {len(messages)} emails. Imported {imported}, updated {updated}.",
        )

    def create_draft(self, request: EmailDraftRequest) -> EmailDraftResponse:
        self._require_connected()
        config = self._configured_config()
        capabilities = _capabilities_from_dict(dict(connector_registry_service.heartbeat_metadata("email").get("capabilities") or config.get("capabilities") or {}))
        if not capabilities.create_draft:
            capabilities = self._discover_capabilities(config)
            connector_registry_service.record_seen("email", {"capabilities": capabilities.model_dump()})
        if not capabilities.create_draft:
            raise EmailConnectorError("Your email provider currently supports reading emails only. Draft creation is not available.")
        if self._provider_requires_recipient(config) and not request.to.strip():
            raise EmailConnectorError("Add a recipient before creating the Gmail draft.")
        if self._is_mock(config):
            return EmailDraftResponse(ok=True, draft_id=f"mock_draft_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", url=None, message="Draft created.")

        payload = {"to": request.to.strip(), "subject": request.subject.strip(), "body": request.body.strip()}
        data = self._call_create_draft(config, payload)
        draft_id = ""
        url = None
        if isinstance(data, dict):
            draft_id = str(data.get("draft_id") or data.get("draftId") or data.get("id") or "")
            url = str(data.get("url") or data.get("web_url") or data.get("webUrl") or "") or None
        if not draft_id:
            raise EmailConnectorError("Draft creation failed.")
        return EmailDraftResponse(ok=True, draft_id=draft_id, url=url, message="Draft created.")

    def search_messages(self, config: dict[str, Any], request: EmailSyncRequest) -> list[NormalizedEmailMessage]:
        if self._is_mock(config):
            return _mock_messages(request)

        payload = {
            "scope": request.scope,
            "query": request.query or "",
            "max_items": min(request.max_items, 100),
        }
        data = self._call_direct_or_tool(config, "/email/search", self._tool_name(config, "search"), payload)
        raw_messages = _extract_list(data, ["messages", "emails", "items", "results"])
        return [_normalize_message(item) for item in raw_messages[: request.max_items] if isinstance(item, dict)]

    def _discover_capabilities(self, config: dict[str, Any]) -> EmailCapabilityResponse:
        if self._is_mock(config):
            return EmailCapabilityResponse(search_emails=True, read_email=True, list_folders=True, create_draft=True, send_email=False)

        attempts: list[dict[str, Any]] = []
        for path in ["/health", "/status", "/email/capabilities", "/capabilities"]:
            try:
                data = self._request(config, "GET", path)
                attempts.append({"path": path, "ok": True})
                capabilities = _capabilities_from_provider(data)
                if any([capabilities.search_emails, capabilities.read_email, capabilities.list_folders, capabilities.create_draft]):
                    return capabilities
            except EmailConnectorError as exc:
                attempts.append({"path": path, "error": str(exc)})

        try:
            data = self._request(config, "POST", "/tools/list", json_payload={})
            capabilities = _capabilities_from_provider(data)
            if any([capabilities.search_emails, capabilities.read_email, capabilities.list_folders, capabilities.create_draft]):
                return capabilities
        except EmailConnectorError as exc:
            attempts.append({"path": "/tools/list", "error": str(exc)})

        for tool_name, arguments in [
            (self._tool_name(config, "test"), {}),
        ]:
            try:
                data = self._call_tool(config, tool_name, arguments)
                capabilities = _capabilities_from_provider(data)
                if any([capabilities.search_emails, capabilities.read_email, capabilities.list_folders, capabilities.create_draft]):
                    return capabilities
            except EmailConnectorError as exc:
                attempts.append({"tool": tool_name, "error": str(exc)})

        if attempts:
            return EmailCapabilityResponse(search_emails=True, read_email=False, list_folders=False, raw={"discovery_attempts": attempts})
        return EmailCapabilityResponse()

    def _call_direct_or_tool(self, config: dict[str, Any], direct_path: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            return self._request(config, "POST", direct_path, json_payload=arguments)
        except EmailConnectorError:
            return self._call_tool(config, tool_name, arguments)

    def _call_tool(self, config: dict[str, Any], tool_name: str, arguments: dict[str, Any]) -> Any:
        data = self._request(config, "POST", "/tools/call", json_payload={"tool": tool_name, "arguments": arguments})
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data

    def _call_create_draft(self, config: dict[str, Any], payload: dict[str, Any]) -> Any:
        try:
            return self._request(config, "POST", "/email/drafts", json_payload=payload)
        except EmailConnectorError as first_error:
            last_error = first_error
        tool_names = [
            self._tool_name(config, "create_draft"),
            "gmail.create_draft",
            "gmail.draft",
            "create_draft",
        ]
        seen: set[str] = set()
        for tool_name in tool_names:
            if tool_name in seen:
                continue
            seen.add(tool_name)
            try:
                return self._call_tool(config, tool_name, payload)
            except EmailConnectorError as error:
                last_error = error
        raise last_error

    def _request(self, config: dict[str, Any], method: str, path: str, json_payload: dict[str, Any] | None = None) -> Any:
        base_url = str(config.get("api_base_url") or "").rstrip("/")
        if not base_url or base_url == "mock":
            raise EmailConnectorError("Email MCP base URL is not configured.")
        try:
            with httpx.Client(base_url=base_url, headers=self._headers(config), timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.request(method, path, json=json_payload)
        except httpx.HTTPError as exc:
            connector_registry_service.record_seen("email", {"last_error": "Email MCP provider did not respond."})
            raise EmailConnectorError("Email MCP provider did not respond.") from exc
        if response.status_code in {401, 403}:
            connector_registry_service.record_seen("email", {"last_error": "Email MCP credentials are invalid or expired."})
            raise EmailConnectorError("Email MCP credentials are invalid or expired.")
        if response.status_code >= 400:
            connector_registry_service.record_seen("email", {"last_error": f"Email MCP provider returned {response.status_code}."})
            raise EmailConnectorError(f"Email MCP provider returned {response.status_code}.")
        try:
            return response.json()
        except ValueError as exc:
            raise EmailConnectorError("Email MCP provider returned non-JSON response.") from exc

    def _headers(self, config: dict[str, Any]) -> dict[str, str]:
        auth_type = str(config.get("auth_type") or "none")
        api_key = str(config.get("api_key") or "")
        if auth_type == "none" or not api_key:
            return {}
        header_name = str(config.get("auth_header_name") or "Authorization")
        if auth_type == "bearer":
            return {header_name: f"Bearer {api_key}"}
        if auth_type == "api_key_header":
            return {header_name: api_key}
        return {}

    def _upsert_email_message(self, config: dict[str, Any], message: NormalizedEmailMessage) -> dict[str, Any]:
        dedupe_key = self._dedupe_key(config, message)
        excerpt = _clean_text(message.body_excerpt or message.snippet)[:EXCERPT_MAX_CHARS]
        provider_name = str(config.get("provider_name") or "Email MCP")
        account_label = str(config.get("account_label") or "")
        content_lines = [
            f"From: {message.from_address}",
            f"Date: {message.date or ''}",
            f"Subject: {message.subject}",
        ]
        if excerpt:
            content_lines.append(f"Excerpt: {excerpt}")
        metadata: dict[str, Any] = {
            "provider": "email_mcp",
            "provider_name": provider_name,
            "account_label": account_label,
            "provider_message_id": message.id,
            "thread_id": message.thread_id,
            "from": message.from_address,
            "to": message.to,
            "cc": message.cc,
            "date": message.date,
            "labels": message.labels,
            "folder": message.folder,
            "has_attachments": message.has_attachments,
            "attachments": [attachment.model_dump() for attachment in message.attachments],
            "url": message.url,
            "dedupe_key": dedupe_key,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
        title = f"Email: {message.subject}" if message.subject else "Email: (no subject)"
        timestamp = _parse_datetime(message.date)
        return self._upsert_event(title, "\n".join(content_lines), metadata, timestamp)

    def _upsert_event(self, title: str, content: str, metadata: dict[str, Any], timestamp: datetime | None) -> dict[str, Any]:
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

    def _dedupe_key(self, config: dict[str, Any], message: NormalizedEmailMessage) -> str:
        provider_name = str(config.get("provider_name") or "Email MCP")
        account_label = str(config.get("account_label") or "")
        if message.id:
            return f"email_mcp:{provider_name}:{account_label}:{message.id}"
        raw = "|".join([message.subject, message.from_address, message.date or "", (message.snippet or message.body_excerpt)[:500]])
        return f"email_mcp:{provider_name}:{account_label}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    def _require_connected(self) -> None:
        if not connector_registry_service.is_enabled("email") or not connector_registry_service.heartbeat_metadata("email").get("connected"):
            raise EmailConnectorError("Email connector is not connected.")

    def _configured_config(self) -> dict[str, Any]:
        config = self._config()
        if not self._is_configured(config):
            raise EmailConnectorError("Email MCP provider is not configured.")
        return config

    def _is_configured(self, config: dict[str, Any]) -> bool:
        if str(config.get("provider_type") or "email_mcp") != "email_mcp":
            return False
        base_url = str(config.get("api_base_url") or "")
        auth_type = str(config.get("auth_type") or "none")
        return bool(config.get("provider_name") and base_url and (auth_type == "none" or config.get("api_key")))

    def _is_mock(self, config: dict[str, Any]) -> bool:
        return str(config.get("api_base_url") or "").strip().lower() == "mock"

    def _tool_name(self, config: dict[str, Any], key: str) -> str:
        mapping = dict(config.get("tool_mapping") or {})
        return str(mapping.get(key) or f"email.{key}")

    def _provider_requires_recipient(self, config: dict[str, Any]) -> bool:
        return bool(config.get("requires_recipient", True))

    def _config(self) -> dict[str, Any]:
        return connector_registry_service.get_config_dict("email")


def _mock_messages(request: EmailSyncRequest) -> list[NormalizedEmailMessage]:
    samples = [
        NormalizedEmailMessage(
            id="mock-001",
            thread_id="mock-thread-001",
            subject="Deployment checklist for MindOS",
            **{"from": "devops@example.com"},
            to=["you@example.com"],
            date="2026-06-04T08:15:00+00:00",
            snippet="Please review the deployment checklist before the next local demo.",
            body_excerpt="Please review the deployment checklist before the next local demo. The main items are connector status, memory sync, and smoke tests.",
            labels=["INBOX"],
            folder="INBOX",
        ),
        NormalizedEmailMessage(
            id="mock-002",
            thread_id="mock-thread-002",
            subject="Unread: API review notes",
            **{"from": "teammate@example.com"},
            to=["you@example.com"],
            date="2026-06-03T16:40:00+00:00",
            snippet="I left notes on the connector API contract and the memory policy.",
            body_excerpt="I left notes on the connector API contract and the memory policy. The read-only connector direction looks good.",
            labels=["INBOX", "UNREAD"],
            folder="INBOX",
        ),
        NormalizedEmailMessage(
            id="mock-003",
            thread_id="mock-thread-003",
            subject="Corporate email MCP rollout",
            **{"from": "platform@example.com"},
            to=["you@example.com"],
            date="2026-06-02T11:05:00+00:00",
            snippet="The internal email MCP endpoint is ready for read-only testing.",
            body_excerpt="The internal email MCP endpoint is ready for read-only testing. Send, delete, and archive tools are not enabled for MindOS.",
            labels=["INBOX"],
            folder="INBOX",
        ),
    ]
    messages = samples
    if request.scope == "unread":
        messages = [message for message in messages if "UNREAD" in message.labels]
    if request.scope == "search" and request.query:
        term = request.query.lower()
        messages = [message for message in messages if term in (message.subject + " " + message.snippet + " " + message.body_excerpt).lower()]
    return messages[: request.max_items]


def _normalize_message(item: dict[str, Any]) -> NormalizedEmailMessage:
    attachments = item.get("attachments") or []
    normalized_attachments = [
        NormalizedEmailAttachment(
            filename=str(attachment.get("filename") or attachment.get("name") or ""),
            mime_type=str(attachment.get("mime_type") or attachment.get("mimeType") or attachment.get("content_type") or ""),
            size=_optional_int(attachment.get("size") or attachment.get("size_bytes")),
        )
        for attachment in attachments
        if isinstance(attachment, dict)
    ]
    labels = _string_list(item.get("labels") or item.get("labelIds") or item.get("folders"))
    folder = str(item.get("folder") or (labels[0] if labels else "") or "") or None
    body_excerpt = str(item.get("body_excerpt") or item.get("bodyExcerpt") or item.get("excerpt") or item.get("body") or "")[:EXCERPT_MAX_CHARS]
    return NormalizedEmailMessage(
        id=str(item.get("id") or item.get("message_id") or item.get("provider_message_id") or item.get("providerMessageId") or ""),
        thread_id=str(item.get("thread_id") or item.get("threadId") or "") or None,
        subject=str(item.get("subject") or ""),
        **{"from": str(item.get("from") or item.get("sender") or item.get("from_address") or "")},
        to=_string_list(item.get("to") or item.get("recipients")),
        cc=_string_list(item.get("cc")),
        date=str(item.get("date") or item.get("received_at") or item.get("receivedAt") or "") or None,
        snippet=str(item.get("snippet") or item.get("preview") or item.get("summary") or "")[:EXCERPT_MAX_CHARS],
        body_excerpt=body_excerpt,
        labels=labels,
        folder=folder,
        has_attachments=bool(item.get("has_attachments") or item.get("hasAttachments") or normalized_attachments),
        attachments=normalized_attachments,
        url=str(item.get("url") or item.get("web_url") or item.get("webUrl") or "") or None,
    )


def _capabilities_from_provider(data: Any) -> EmailCapabilityResponse:
    raw = data if isinstance(data, dict) else {"value": data}
    tools = _extract_list(raw, ["tools", "capabilities", "items"])
    names = {str(tool.get("name") or tool.get("id") or tool).lower() for tool in tools if isinstance(tool, (dict, str))}
    text = " ".join(names) + " " + " ".join(str(key).lower() for key in raw.keys())
    return EmailCapabilityResponse(
        search_emails=bool(raw.get("search_emails") or raw.get("search") or "email.search" in text or "search" in text),
        read_email=bool(raw.get("read_email") or raw.get("get") or "email.get" in text or "read" in text),
        list_folders=bool(raw.get("list_folders") or raw.get("folders") or "email.list_folders" in text or "folder" in text),
        create_draft=bool(raw.get("create_draft") or raw.get("createDraft") or "email.create_draft" in text or "gmail.create_draft" in text or "gmail.draft" in text or "create_draft" in text),
        send_email=bool(raw.get("send_email") or "email.send" in text or "send" in text),
        delete_email=bool(raw.get("delete_email") or "email.delete" in text or "delete" in text),
        modify_email=bool(raw.get("modify_email") or "archive" in text or "mark" in text or "modify" in text),
        raw={"provider_capabilities": raw},
    )


def _capabilities_from_dict(value: dict[str, Any]) -> EmailCapabilityResponse:
    return EmailCapabilityResponse(
        search_emails=bool(value.get("search_emails")),
        read_email=bool(value.get("read_email")),
        list_folders=bool(value.get("list_folders")),
        create_draft=bool(value.get("create_draft")),
        send_email=bool(value.get("send_email")),
        delete_email=bool(value.get("delete_email")),
        modify_email=bool(value.get("modify_email")),
        raw=dict(value.get("raw") or {}),
    )


def _extract_list(data: Any, keys: list[str]) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    result = data.get("result")
    if isinstance(result, (dict, list)):
        return _extract_list(result, keys)
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_error(error: Exception) -> str:
    return re.sub(r"(Bearer|Token|Api-Key|Authorization)\s+[A-Za-z0-9._~+/=-]+", r"\1 [redacted]", str(error))[:200]


email_service = EmailService()
