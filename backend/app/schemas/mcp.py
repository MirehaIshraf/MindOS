"""Pydantic schemas for MCP server/client API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# --- Server status ---

class McpServerStatus(BaseModel):
    server_id: str
    name: str
    description: str
    version: str = "1.0.0"
    enabled: bool = False
    connected: bool = False
    configured: bool = False
    tool_count: int = 0
    categories: list[str] = []
    config: dict[str, Any] = {}


class McpServerListResponse(BaseModel):
    servers: list[McpServerStatus]


class McpServerToggleRequest(BaseModel):
    enabled: bool


class McpServerToggleResponse(BaseModel):
    server_id: str
    enabled: bool
    message: str = ""


# --- Server config ---

class McpServerConfigRequest(BaseModel):
    config: dict[str, Any]


class McpServerConfigResponse(BaseModel):
    server_id: str
    config: dict[str, Any]
    configured: bool
    message: str = ""


# --- Tool info ---

class McpToolInfo(BaseModel):
    name: str
    description: str
    side_effect: bool = False
    category: str = "general"
    parameters: list[dict[str, Any]] = []


class McpToolListResponse(BaseModel):
    tools: list[McpToolInfo]
    server_id: str


# --- Tool call ---

class McpToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}
    confirmed: bool = False


class McpToolCallResponse(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    requires_confirmation: bool = False
    preview: dict[str, Any] | None = None


# --- Chat integration ---

class McpChatToolCall(BaseModel):
    """A single tool call parsed from LLM response."""
    tool_name: str
    arguments: dict[str, Any] = {}


class McpChatToolResult(BaseModel):
    """Result of executing a tool call, fed back to the LLM."""
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
    requires_confirmation: bool = False
