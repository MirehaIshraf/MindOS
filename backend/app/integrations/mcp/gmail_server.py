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

from typing import Any

from app.integrations.mcp.protocol import (
    McpToolCallResult,
    McpToolDefinition,
    McpToolParameter,
)
from app.schemas.file_index import IndexedFileAttachmentReference, IndexedFileSearchRequest
from app.schemas.gmail import GmailDraftRequest, GmailSendRequest
from app.services.file_index_service import file_index_service
from app.services.gmail_service import GmailConnectorError, gmail_service

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

    def search_attachments(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search connected, indexed, attachable files. Returns plain dicts."""
        if not query or not query.strip():
            return []
        try:
            response = file_index_service.search(
                IndexedFileSearchRequest(
                    query=query.strip(),
                    attachable_only=True,
                    connected_sources_only=True,
                    limit=limit,
                )
            )
        except Exception:
            return []
        return [
            {
                "source_id": match.source_id,
                "relative_path": match.relative_path,
                "file_name": match.file_name,
                "extension": match.extension,
                "size_bytes": match.size_bytes,
                "score": match.score,
            }
            for match in response.matches
        ]

    def resolve_attachment_candidates(self, attachment_query: str, provided_refs: Any) -> dict[str, Any]:
        """Decide attachment outcome: chosen ref(s), multiple candidates, or none.

        Returns {indexed_attachments:[{source_id,relative_path}], attachments:[name], candidates:[...], note}.
        """
        result: dict[str, Any] = {"indexed_attachments": [], "attachments": [], "candidates": [], "note": None}

        explicit = self._to_refs(provided_refs)
        if explicit:
            result["indexed_attachments"] = [{"source_id": r.source_id, "relative_path": r.relative_path} for r in explicit]
            result["attachments"] = [r.relative_path.replace("\\", "/").split("/")[-1] for r in explicit]
            return result

        if not attachment_query or not attachment_query.strip():
            return result

        matches = self.search_attachments(attachment_query)
        if not matches:
            result["note"] = "No matching connected file was found."
            return result

        top = matches[0]
        strong = len(matches) == 1 or top["score"] >= matches[1]["score"] * 1.5
        if strong:
            result["indexed_attachments"] = [{"source_id": top["source_id"], "relative_path": top["relative_path"]}]
            result["attachments"] = [top["file_name"]]
        else:
            result["candidates"] = matches[:5]
            result["note"] = "Multiple matching files were found. Ask the user which one to attach."
        return result

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
        resolved = self.resolve_attachment_candidates(str(args.get("attachment_query", "")), args.get("indexed_attachments"))
        return McpToolCallResult(
            success=True,
            data={
                "to": str(args.get("to", "")).strip(),
                "subject": str(args.get("subject", "")).strip(),
                "body": str(args.get("body", "")).strip(),
                "cc": self._as_list(args.get("cc")),
                "bcc": self._as_list(args.get("bcc")),
                "attachments": resolved["attachments"],
                "indexed_attachments": resolved["indexed_attachments"],
                "candidates": resolved["candidates"],
                "note": resolved["note"],
                "action": "create_draft",
            },
        )

    def _create_draft(self, args: dict[str, Any]) -> McpToolCallResult:
        guard = self._require_capability("create_draft")
        if guard:
            return guard
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
        request = GmailSendRequest(
            to=self._as_list(args.get("to")),
            subject=str(args.get("subject", "")),
            body=str(args.get("body", "")),
            cc=self._as_list(args.get("cc")),
            bcc=self._as_list(args.get("bcc")),
            indexed_attachments=self._to_refs(args.get("indexed_attachments")),
            confirmation=True,  # Only reached after the user confirms (side-effect gate).
        )
        response = gmail_service.send_message(request)
        return McpToolCallResult(success=True, data=response.model_dump())


gmail_mcp_server = GmailMcpServer()
