"""MCP Client — connects to MCP servers and routes tool calls.

The client discovers tools from registered servers, provides tool schemas
to the LLM for function-calling, and routes LLM tool calls to the
appropriate server.

Safety: Side-effect tool calls are blocked until the user confirms.
Read-only calls pass through immediately.
"""

from __future__ import annotations

from typing import Any

from app.integrations.mcp.protocol import (
    McpToolCallResult,
    McpToolDefinition,
    McpServerInfo,
    tool_to_openai_function,
)


class McpClient:
    """Central MCP client that manages connections to all registered MCP servers."""

    def __init__(self) -> None:
        self._servers: dict[str, Any] = {}  # server_id -> server instance
        self._tool_map: dict[str, str] = {}  # tool_name -> server_id
        self._enabled_servers: set[str] = set()
        self._server_configs: dict[str, dict[str, Any]] = {}  # server_id -> config dict

    def register_server(self, server_id: str, server: Any) -> None:
        """Register an MCP server instance."""
        self._servers[server_id] = server
        for tool in server.list_tools():
            self._tool_map[tool.name] = server_id

    def enable_server(self, server_id: str) -> bool:
        """Enable an MCP server so its tools are available to the LLM."""
        if server_id in self._servers:
            self._enabled_servers.add(server_id)
            return True
        return False

    def disable_server(self, server_id: str) -> bool:
        """Disable an MCP server so its tools are hidden from the LLM."""
        if server_id in self._enabled_servers:
            self._enabled_servers.discard(server_id)
            return True
        return False

    def is_server_enabled(self, server_id: str) -> bool:
        return server_id in self._enabled_servers

    def get_server_config(self, server_id: str) -> dict[str, Any]:
        """Get the stored config for a server."""
        return self._server_configs.get(server_id, {})

    def update_server_config(self, server_id: str, config: dict[str, Any]) -> bool:
        """Update the stored config for a server and apply it."""
        if server_id not in self._servers:
            return False
        self._server_configs[server_id] = config
        server = self._servers[server_id]
        if hasattr(server, "apply_config"):
            server.apply_config(config)
        return True

    def is_server_configured(self, server_id: str) -> bool:
        """Check if a server has its required configuration set."""
        server = self._servers.get(server_id)
        if server is None:
            return False
        required = getattr(server, "REQUIRED_CONFIG_KEYS", [])
        if not required:
            return True
        config = self._server_configs.get(server_id, {})
        return all(config.get(key) for key in required)

    def get_server_info(self, server_id: str) -> McpServerInfo | None:
        """Get info about a registered server."""
        server = self._servers.get(server_id)
        if server is None:
            return None
        tools = server.list_tools()
        categories = sorted({t.category for t in tools})
        config = self._server_configs.get(server_id, {})
        configured = self.is_server_configured(server_id)
        return McpServerInfo(
            server_id=server_id,
            name=getattr(server, "SERVER_NAME", server_id),
            description=getattr(server, "SERVER_DESCRIPTION", ""),
            enabled=server_id in self._enabled_servers,
            connected=True,
            configured=configured,
            tool_count=len(tools),
            categories=categories,
            config=config,
        )

    def list_servers(self) -> list[McpServerInfo]:
        """List all registered servers with their status."""
        return [self.get_server_info(sid) for sid in self._servers]

    def list_available_tools(self) -> list[McpToolDefinition]:
        """List all tools from enabled servers only."""
        tools: list[McpToolDefinition] = []
        for server_id in self._enabled_servers:
            server = self._servers.get(server_id)
            if server:
                tools.extend(server.list_tools())
        return tools

    def get_tool_definitions_for_llm(self) -> list[dict[str, Any]]:
        """Get OpenAI-style function definitions for all enabled tools.
        
        Used to provide tool schemas to the LLM for function-calling.
        Only tools from enabled servers are included.
        """
        return [tool_to_openai_function(tool) for tool in self.list_available_tools()]

    def call_tool(self, tool_name: str, arguments: dict[str, Any], *, confirmed: bool = False) -> McpToolCallResult:
        """Call a tool on the appropriate MCP server.

        Args:
            tool_name: The tool to call (e.g. 'fs.scan_folder').
            arguments: The arguments for the tool.
            confirmed: Whether the user has confirmed a side-effect operation.

        Returns:
            McpToolCallResult with success, data, and confirmation status.
        """
        server_id = self._tool_map.get(tool_name)
        if server_id is None:
            return McpToolCallResult(success=False, error=f"Unknown tool: {tool_name}")

        if server_id not in self._enabled_servers:
            return McpToolCallResult(
                success=False,
                error=f"MCP server '{server_id}' is disabled. Enable it in Connectors to use {tool_name}.",
            )

        server = self._servers[server_id]
        tool_def = self._find_tool(tool_name)

        # Block side-effect tools without confirmation
        if tool_def and tool_def.side_effect and not confirmed:
            return McpToolCallResult(
                success=False,
                error=f"Tool '{tool_name}' modifies files and requires user confirmation before execution.",
                requires_confirmation=True,
                preview=self._get_preview(tool_name, arguments, server),
            )

        return server.call_tool(tool_name, arguments)

    def call_tool_readonly(self, tool_name: str, arguments: dict[str, Any]) -> McpToolCallResult:
        """Call a read-only tool (no confirmation needed)."""
        tool_def = self._find_tool(tool_name)
        if tool_def and tool_def.side_effect:
            return McpToolCallResult(
                success=False,
                error=f"Tool '{tool_name}' is a side-effect operation. Use call_tool with confirmed=True.",
                requires_confirmation=True,
            )
        return self.call_tool(tool_name, arguments, confirmed=False)

    def get_side_effect_tools(self) -> list[McpToolDefinition]:
        """List tools that modify state and require confirmation."""
        return [t for t in self.list_available_tools() if t.side_effect]

    def get_readonly_tools(self) -> list[McpToolDefinition]:
        """List tools that are safe to call without confirmation."""
        return [t for t in self.list_available_tools() if not t.side_effect]

    def _find_tool(self, tool_name: str) -> McpToolDefinition | None:
        for tool in self.list_available_tools():
            if tool.name == tool_name:
                return tool
        return None

    def _get_preview(self, tool_name: str, arguments: dict[str, Any], server: Any) -> dict[str, Any] | None:
        """Try to get a preview for a side-effect tool call."""
        # For organize_plan, the preview is built into the result
        # For create_folder/move_file, construct a simple preview
        if tool_name == "fs.create_folder":
            return {"action": "create_folder", "root_path": arguments.get("root_path"), "folder_path": arguments.get("folder_path")}
        if tool_name == "fs.move_file":
            return {"action": "move_file", "root_path": arguments.get("root_path"), "from_path": arguments.get("from_path"), "to_path": arguments.get("to_path")}
        if tool_name in ("gmail.create_draft", "gmail.send_email"):
            attachment_paths = arguments.get("attachment_paths") or []
            indexed = arguments.get("indexed_attachments") or []
            names = [str(p).replace("\\", "/").split("/")[-1] for p in attachment_paths if str(p).strip()]
            names += [
                str(a.get("relative_path", "")).replace("\\", "/").split("/")[-1]
                for a in indexed
                if isinstance(a, dict) and a.get("relative_path")
            ]
            return {
                "action_type": "send_email" if tool_name == "gmail.send_email" else "create_draft",
                "to": arguments.get("to"),
                "cc": arguments.get("cc") or [],
                "bcc": arguments.get("bcc") or [],
                "subject": arguments.get("subject"),
                "body": arguments.get("body"),
                "attachments": names,
            }
        return None


# Global singleton
mcp_client = McpClient()
