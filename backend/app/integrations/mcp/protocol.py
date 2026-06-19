"""MCP Protocol types — JSON-RPC 2.0 based communication between MCP client and server.

Follows the Model Context Protocol specification:
- tools/list: discover available tools
- tools/call: invoke a tool with arguments
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------

@dataclass
class JsonRpcRequest:
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class JsonRpcResponse:
    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Tool description types
# ---------------------------------------------------------------------------

@dataclass
class McpToolParameter:
    name: str
    type: str  # JSON Schema type: string, integer, boolean, array, object
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class McpToolDefinition:
    """Schema for a single tool exposed by an MCP server."""
    name: str
    description: str
    parameters: list[McpToolParameter] = field(default_factory=list)
    side_effect: bool = False  # True if the tool modifies state (requires confirmation)
    category: str = "general"  # Grouping: filesystem, gmail, github, etc.


# ---------------------------------------------------------------------------
# Tool call result
# ---------------------------------------------------------------------------

@dataclass
class McpToolCallResult:
    success: bool
    data: Any = None
    error: str | None = None
    requires_confirmation: bool = False
    preview: dict[str, Any] | None = None  # For side-effect tools, show preview before executing


# ---------------------------------------------------------------------------
# Server info
# ---------------------------------------------------------------------------

@dataclass
class McpServerInfo:
    server_id: str
    name: str
    description: str
    version: str = "1.0.0"
    enabled: bool = False
    connected: bool = False
    configured: bool = False
    tool_count: int = 0
    categories: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


def tool_to_json_schema(tool: McpToolDefinition) -> dict[str, Any]:
    """Convert a McpToolDefinition to a JSON Schema dict for LLM function-calling."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in tool.parameters:
        prop: dict[str, Any] = {"type": param.type, "description": param.description}
        if param.enum:
            prop["enum"] = param.enum
        if param.default is not None:
            prop["default"] = param.default
        properties[param.name] = prop
        if param.required:
            required.append(param.name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def tool_to_openai_function(tool: McpToolDefinition) -> dict[str, Any]:
    """Convert a McpToolDefinition to OpenAI-style function definition for tool-calling."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool_to_json_schema(tool),
        },
    }
