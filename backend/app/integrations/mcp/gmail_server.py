"""MCP Gmail Server — exposes safe Gmail tools (recent / draft / send).

Wraps MindOS's existing GmailService behind the MCP protocol. Read tools
(recent_emails) run immediately; write tools (create_draft, send_email) are
marked side_effect=True, so the MCP client blocks them until the user confirms.

Every handler re-checks Gmail connection/capabilities — the LLM caller is never
trusted, and nothing is sent without a confirmed call.
"""

from __future__ import annotations

from typing import Any

from app.integrations.mcp.protocol import (
    McpToolCallResult,
    McpToolDefinition,
    McpToolParameter,
)
from app.schemas.gmail import GmailDraftRequest, GmailSendRequest
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
        name="gmail.create_draft",
        description="Create a draft email in Gmail (it is NOT sent). Always show the drafted to/subject/body to the user first. Requires confirmation.",
        parameters=[
            McpToolParameter(name="to", type="string", description="Recipient email address."),
            McpToolParameter(name="subject", type="string", description="Email subject."),
            McpToolParameter(name="body", type="string", description="Email body text."),
            McpToolParameter(name="cc", type="array", description="Optional CC email addresses.", required=False),
            McpToolParameter(name="bcc", type="array", description="Optional BCC email addresses.", required=False),
        ],
        side_effect=True,
        category="gmail",
    ),
    McpToolDefinition(
        name="gmail.send_email",
        description="Send an email from the connected Gmail account. Always show the to/subject/body to the user and get confirmation first. Requires confirmation.",
        parameters=[
            McpToolParameter(name="to", type="string", description="Recipient email address."),
            McpToolParameter(name="subject", type="string", description="Email subject."),
            McpToolParameter(name="body", type="string", description="Email body text."),
            McpToolParameter(name="cc", type="array", description="Optional CC email addresses.", required=False),
            McpToolParameter(name="bcc", type="array", description="Optional BCC email addresses.", required=False),
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
                error="Gmail is not connected. Connect your Gmail account in the Connectors page first.",
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
        )
        response = gmail_service.create_draft(request)
        return McpToolCallResult(success=True, data=response.model_dump())

    def _send_email(self, args: dict[str, Any]) -> McpToolCallResult:
        guard = self._require_capability("send_email")
        if guard:
            return guard
        recipients = self._as_list(args.get("to"))
        request = GmailSendRequest(
            to=recipients,
            subject=str(args.get("subject", "")),
            body=str(args.get("body", "")),
            cc=self._as_list(args.get("cc")),
            bcc=self._as_list(args.get("bcc")),
            confirmation=True,  # Only reached after the user confirms (side-effect gate).
        )
        response = gmail_service.send_message(request)
        return McpToolCallResult(success=True, data=response.model_dump())


gmail_mcp_server = GmailMcpServer()
