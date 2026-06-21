"""MCP Gmail Server — exposes safe Gmail tools (recent / prepare / draft / send).

Wraps MindOS's existing GmailService behind the MCP protocol. Read/preview tools
(recent_emails, prepare_draft) run immediately; write tools (create_draft,
send_email) are marked side_effect=True, so the MCP client blocks them until the
user confirms.

Attachments are restricted to connected, indexed files (via FileIndexService) —
never arbitrary absolute paths. Every handler re-checks Gmail connection — the
LLM caller is never trusted, and nothing is sent without a confirmed call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.integrations.mcp.protocol import (
    McpToolCallResult,
    McpToolDefinition,
    McpToolParameter,
)
from app.schemas.file_index import IndexedFileAttachmentReference
from app.schemas.gmail import GmailDraftRequest, GmailSendRequest
from app.services.gmail_service import GMAIL_BLOCKED_ATTACHMENT_EXTENSIONS, GmailConnectorError, gmail_service
from app.services.mcp_config_service import mcp_config_service
from app.services.mcp_file_index_service import mcp_file_index_service

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

GMAIL_TOOLS: list[McpToolDefinition] = [
    McpToolDefinition(
        name="gmail.recent_emails",
        description="List the most recent emails in the connected Gmail inbox (subject, sender, date, snippet). Read-only.",
        parameters=[
            McpToolParameter(name="limit", type="integer", description="How many recent emails to return (1-25).", required=False, default=5),
        ],
        side_effect=False,
        category="gmail",
    ),
    McpToolDefinition(
        name="gmail.prepare_draft",
        description=(
            "Preview an email draft WITHOUT creating it. Optionally searches connected indexed files for an "
            "attachment (e.g. a resume). Returns the resolved to/subject/body and any attachment candidates. "
            "Always call this before gmail.create_draft so the user can review. Read-only."
        ),
        parameters=[
            McpToolParameter(name="to", type="string", description="Recipient email address."),
            McpToolParameter(name="subject", type="string", description="Email subject."),
            McpToolParameter(name="body", type="string", description="Email body text."),
            McpToolParameter(name="cc", type="array", description="Optional CC email addresses.", required=False),
            McpToolParameter(name="bcc", type="array", description="Optional BCC email addresses.", required=False),
            McpToolParameter(name="attachment_query", type="string", description="Optional keyword to find a connected indexed file to attach (e.g. 'resume').", required=False),
            McpToolParameter(name="indexed_attachments", type="array", description="Optional already-chosen indexed file references {source_id, relative_path}.", required=False),
        ],
        side_effect=False,
        category="gmail",
    ),
    McpToolDefinition(
        name="gmail.create_draft",
        description="Create a draft email in Gmail (it is NOT sent). Always preview first. Requires confirmation.",
        parameters=[
            McpToolParameter(name="to", type="string", description="Recipient email address."),
            McpToolParameter(name="subject", type="string", description="Email subject."),
            McpToolParameter(name="body", type="string", description="Email body text."),
            McpToolParameter(name="cc", type="array", description="Optional CC email addresses.", required=False),
            McpToolParameter(name="bcc", type="array", description="Optional BCC email addresses.", required=False),
            McpToolParameter(name="indexed_attachments", type="array", description="Optional connected indexed file references {source_id, relative_path}.", required=False),
        ],
        side_effect=True,
        category="gmail",
    ),
    McpToolDefinition(
        name="gmail.send_email",
        description="Send an email from the connected Gmail account. Always preview first and get confirmation. Requires confirmation.",
        parameters=[
            McpToolParameter(name="to", type="string", description="Recipient email address."),
            McpToolParameter(name="subject", type="string", description="Email subject."),
            McpToolParameter(name="body", type="string", description="Email body text."),
            McpToolParameter(name="cc", type="array", description="Optional CC email addresses.", required=False),
            McpToolParameter(name="bcc", type="array", description="Optional BCC email addresses.", required=False),
            McpToolParameter(name="indexed_attachments", type="array", description="Optional connected indexed file references {source_id, relative_path}.", required=False),
        ],
        side_effect=True,
        category="gmail",
    ),
]


# ---------------------------------------------------------------------------
# Gmail MCP Server
# ---------------------------------------------------------------------------

class GmailMcpServer:
    """MCP server for Gmail. All operations go through the existing GmailService,
    which enforces OAuth scopes, attachment limits, and send confirmation."""

    SERVER_ID = "gmail"
    SERVER_NAME = "Gmail MCP"
    SERVER_DESCRIPTION = "Read recent emails and create/send drafts from the connected Gmail account."
    REQUIRED_CONFIG_KEYS: list[str] = []  # Configured via OAuth in Connectors, not MCP config.

    def apply_config(self, config: dict[str, Any]) -> None:  # No MCP-level config needed.
        return None

    def list_tools(self) -> list[McpToolDefinition]:
        return list(GMAIL_TOOLS)

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolCallResult:
        handler = {
            "gmail.recent_emails": self._recent_emails,
            "gmail.prepare_draft": self._prepare_draft,
            "gmail.create_draft": self._create_draft,
            "gmail.send_email": self._send_email,
        }.get(tool_name)
        if handler is None:
            return McpToolCallResult(success=False, error=f"Unknown tool: {tool_name}")
        try:
            return handler(arguments)
        except GmailConnectorError as error:
            return McpToolCallResult(success=False, error=str(error))
        except Exception as error:
            return McpToolCallResult(success=False, error=str(error))

    # ------------------------------------------------------------------
    # Guards & helpers
    # ------------------------------------------------------------------

    def _require_capability(self, capability: str | None = None) -> McpToolCallResult | None:
        status = gmail_service.status()
        if not status.connected:
            return McpToolCallResult(
                success=False,
                error="Gmail is not connected. Connect Gmail in Connectors first.",
            )
        if capability and not status.capabilities.get(capability):
            return McpToolCallResult(
                success=False,
                error=f"The connected Gmail account is missing the '{capability}' permission. Reconnect Gmail with compose access in Connectors.",
            )
        return None

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def _to_refs(value: Any) -> list[IndexedFileAttachmentReference]:
        refs: list[IndexedFileAttachmentReference] = []
        for item in value or []:
            if isinstance(item, dict) and item.get("source_id") and item.get("relative_path"):
                refs.append(IndexedFileAttachmentReference(source_id=str(item["source_id"]), relative_path=str(item["relative_path"])))
        return refs

    @staticmethod
    def _mcp_root() -> Path | None:
        root = str((mcp_config_service.get_filesystem_config() or {}).get("root_path") or "").strip()
        if not root:
            return None
        try:
            resolved = Path(root).resolve()
            return resolved if resolved.is_dir() else None
        except Exception:
            return None

    def search_attachments(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search the File System MCP index for attachable, non-missing files."""
        if not query or not query.strip():
            return []
        try:
            matches = mcp_file_index_service.search_files(query.strip(), limit=limit * 3)
        except Exception:
            return []
        results: list[dict[str, Any]] = []
        for match in matches:
            extension = str(match.get("extension") or "").lower()
            if extension in GMAIL_BLOCKED_ATTACHMENT_EXTENSIONS:
                continue
            results.append(
                {
                    "relative_path": match.get("relative_path"),
                    "file_name": match.get("file_name"),
                    "extension": extension,
                    "score": float(match.get("score") or 0),
                }
            )
            if len(results) >= limit:
                break
        return results

    def resolve_attachment_candidates(self, attachment_query: str, provided_paths: Any = None) -> dict[str, Any]:
        """Decide attachment outcome from the MCP index: chosen path, candidates, or none.

        Returns {attachment_paths:[rel], attachments:[name], candidates:[...], note}.
        """
        result: dict[str, Any] = {"attachment_paths": [], "attachments": [], "candidates": [], "note": None}

        explicit = [str(p).strip() for p in (provided_paths or []) if str(p).strip()]
        if explicit:
            result["attachment_paths"] = explicit
            result["attachments"] = [p.replace("\\", "/").split("/")[-1] for p in explicit]
            return result

        if not attachment_query or not attachment_query.strip():
            return result

        matches = self.search_attachments(attachment_query)
        if not matches:
            result["note"] = "No matching file was found in the indexed folder."
            return result

        top = matches[0]
        strong = len(matches) == 1 or top["score"] >= matches[1]["score"] * 1.1
        if strong:
            result["attachment_paths"] = [top["relative_path"]]
            result["attachments"] = [top["file_name"]]
        else:
            result["candidates"] = matches[:5]
            result["note"] = "Multiple matching files were found. Ask the user which one to attach."
        return result

    def _read_attachment_payloads(self, attachment_paths: Any) -> list[dict[str, Any]]:
        """Read files from inside the configured MCP root into Gmail attachment payloads."""
        paths = [str(p).strip() for p in (attachment_paths or []) if str(p).strip()]
        if not paths:
            return []
        root = self._mcp_root()
        if root is None:
            raise GmailConnectorError("File System MCP root is not configured, so I cannot read the attachment.")
        payloads: list[dict[str, Any]] = []
        for raw in paths:
            candidate = Path(raw)
            target = (candidate if candidate.is_absolute() else (root / raw)).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise GmailConnectorError(f"Attachment is outside the allowed folder: {raw}")
            if not target.exists() or not target.is_file():
                raise GmailConnectorError(f"Attachment file was not found: {target.name}")
            if target.stat().st_size > MAX_ATTACHMENT_BYTES:
                raise GmailConnectorError(f"Attachment exceeds the 20 MB limit: {target.name}")
            payloads.append({"filename": target.name, "content": target.read_bytes(), "size": target.stat().st_size})
        return payloads

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _recent_emails(self, args: dict[str, Any]) -> McpToolCallResult:
        guard = self._require_capability("read_email")
        if guard:
            return guard
        limit = int(args.get("limit", 5) or 5)
        response = gmail_service.list_recent_emails(limit)
        return McpToolCallResult(success=True, data=response.model_dump())

    def _prepare_draft(self, args: dict[str, Any]) -> McpToolCallResult:
        guard = self._require_capability("create_draft")
        if guard:
            return guard
        resolved = self.resolve_attachment_candidates(str(args.get("attachment_query", "")), args.get("attachment_paths"))
        return McpToolCallResult(
            success=True,
            data={
                "to": str(args.get("to", "")).strip(),
                "subject": str(args.get("subject", "")).strip(),
                "body": str(args.get("body", "")).strip(),
                "cc": self._as_list(args.get("cc")),
                "bcc": self._as_list(args.get("bcc")),
                "attachments": resolved["attachments"],
                "attachment_paths": resolved["attachment_paths"],
                "candidates": resolved["candidates"],
                "note": resolved["note"],
                "action": "create_draft",
            },
        )

    def _create_draft(self, args: dict[str, Any]) -> McpToolCallResult:
        guard = self._require_capability("create_draft")
        if guard:
            return guard
        attachments = self._read_attachment_payloads(args.get("attachment_paths"))
        if attachments:
            response = gmail_service.create_draft_with_attachments(
                to=self._as_list(args.get("to")),
                subject=str(args.get("subject", "")),
                body=str(args.get("body", "")),
                cc=self._as_list(args.get("cc")),
                bcc=self._as_list(args.get("bcc")),
                attachments=attachments,
            )
        else:
            request = GmailDraftRequest(
                to=str(args.get("to", "")),
                subject=str(args.get("subject", "")),
                body=str(args.get("body", "")),
                cc=self._as_list(args.get("cc")),
                bcc=self._as_list(args.get("bcc")),
                indexed_attachments=self._to_refs(args.get("indexed_attachments")),
            )
            response = gmail_service.create_draft(request)
        return McpToolCallResult(success=True, data=response.model_dump())

    def _send_email(self, args: dict[str, Any]) -> McpToolCallResult:
        guard = self._require_capability("send_email")
        if guard:
            return guard
        attachments = self._read_attachment_payloads(args.get("attachment_paths"))
        recipients = self._as_list(args.get("to"))
        if attachments:
            response = gmail_service.send_message_with_attachments(
                to=recipients,
                subject=str(args.get("subject", "")),
                body=str(args.get("body", "")),
                confirmation=True,  # Only reached after the user confirms (side-effect gate).
                cc=self._as_list(args.get("cc")),
                bcc=self._as_list(args.get("bcc")),
                attachments=attachments,
            )
        else:
            request = GmailSendRequest(
                to=recipients,
                subject=str(args.get("subject", "")),
                body=str(args.get("body", "")),
                cc=self._as_list(args.get("cc")),
                bcc=self._as_list(args.get("bcc")),
                indexed_attachments=self._to_refs(args.get("indexed_attachments")),
                confirmation=True,
            )
            response = gmail_service.send_message(request)
        return McpToolCallResult(success=True, data=response.model_dump())


gmail_mcp_server = GmailMcpServer()
