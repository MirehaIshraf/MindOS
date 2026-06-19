"""MCP API routes — server status, tool discovery, tool execution."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.integrations.mcp.client import mcp_client
from app.integrations.mcp.protocol import McpToolDefinition
from app.schemas.mcp import (
    McpServerConfigRequest,
    McpServerConfigResponse,
    McpServerListResponse,
    McpServerStatus,
    McpServerToggleRequest,
    McpServerToggleResponse,
    McpToolCallRequest,
    McpToolCallResponse,
    McpToolInfo,
    McpToolListResponse,
)

router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = logging.getLogger(__name__)


@router.get("/servers", response_model=McpServerListResponse)
def list_mcp_servers() -> McpServerListResponse:
    """List all registered MCP servers with their status."""
    servers = []
    for info in mcp_client.list_servers():
        servers.append(McpServerStatus(
            server_id=info.server_id,
            name=info.name,
            description=info.description,
            version=info.version,
            enabled=info.enabled,
            connected=info.connected,
            configured=info.configured,
            tool_count=info.tool_count,
            categories=info.categories,
            config=info.config,
        ))
    return McpServerListResponse(servers=servers)


@router.get("/servers/{server_id}", response_model=McpServerStatus)
def get_mcp_server(server_id: str) -> McpServerStatus:
    """Get status of a single MCP server."""
    info = mcp_client.get_server_info(server_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found.")
    return McpServerStatus(
        server_id=info.server_id,
        name=info.name,
        description=info.description,
        version=info.version,
        enabled=info.enabled,
        connected=info.connected,
        configured=info.configured,
        tool_count=info.tool_count,
        categories=info.categories,
        config=info.config,
    )


@router.get("/servers/{server_id}/config", response_model=McpServerConfigResponse)
def get_mcp_server_config(server_id: str) -> McpServerConfigResponse:
    """Get the configuration for an MCP server."""
    info = mcp_client.get_server_info(server_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found.")
    return McpServerConfigResponse(
        server_id=server_id,
        config=info.config,
        configured=info.configured,
        message="" if info.configured else "Configuration required before enabling this server.",
    )


@router.post("/servers/{server_id}/config", response_model=McpServerConfigResponse)
def update_mcp_server_config(server_id: str, request: McpServerConfigRequest) -> McpServerConfigResponse:
    """Update the configuration for an MCP server."""
    from pathlib import Path

    info = mcp_client.get_server_info(server_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found.")

    # Pre-validate root_path for filesystem server
    if server_id == "filesystem":
        root_path = request.config.get("root_path", "")
        if root_path:
            root = Path(root_path)
            if not root.is_absolute():
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid root path: '{root_path}' is not an absolute path. "
                    f"Please provide a full path like 'E:\\Demo' or 'C:\\Users\\YourName\\Documents'.",
                )
            if not root.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid root path: '{root_path}' does not exist. "
                    f"Please make sure the directory exists on your system.",
                )
            if not root.is_dir():
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid root path: '{root_path}' is not a directory. "
                    f"Please provide a folder path, not a file.",
                )

    ok = mcp_client.update_server_config(server_id, request.config)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update server configuration.")
    updated_info = mcp_client.get_server_info(server_id)
    return McpServerConfigResponse(
        server_id=server_id,
        config=updated_info.config if updated_info else request.config,
        configured=updated_info.configured if updated_info else False,
        message="Configuration saved." if updated_info and updated_info.configured else "Configuration saved but incomplete — required fields are missing.",
    )


@router.post("/servers/{server_id}/toggle", response_model=McpServerToggleResponse)
def toggle_mcp_server(server_id: str, request: McpServerToggleRequest) -> McpServerToggleResponse:
    """Enable or disable an MCP server."""
    info = mcp_client.get_server_info(server_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found.")

    if request.enabled:
        ok = mcp_client.enable_server(server_id)
        return McpServerToggleResponse(
            server_id=server_id,
            enabled=True,
            message=f"MCP server '{info.name}' enabled. {info.tool_count} tools are now available.",
        )
    else:
        mcp_client.disable_server(server_id)
        return McpServerToggleResponse(
            server_id=server_id,
            enabled=False,
            message=f"MCP server '{info.name}' disabled. Tools are hidden from chat.",
        )


@router.get("/servers/{server_id}/tools", response_model=McpToolListResponse)
def list_mcp_server_tools(server_id: str) -> McpToolListResponse:
    """List tools exposed by a specific MCP server."""
    info = mcp_client.get_server_info(server_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found.")

    # Get tools from the server directly
    server = mcp_client._servers.get(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' instance not found.")

    tools = []
    for tool in server.list_tools():
        params = []
        for p in tool.parameters:
            param_dict = {"name": p.name, "type": p.type, "description": p.description, "required": p.required}
            if p.default is not None:
                param_dict["default"] = p.default
            if p.enum:
                param_dict["enum"] = p.enum
            params.append(param_dict)
        tools.append(McpToolInfo(
            name=tool.name,
            description=tool.description,
            side_effect=tool.side_effect,
            category=tool.category,
            parameters=params,
        ))
    return McpToolListResponse(tools=tools, server_id=server_id)


@router.get("/tools", response_model=McpToolListResponse)
def list_available_mcp_tools() -> McpToolListResponse:
    """List all tools from enabled MCP servers that are available to the LLM."""
    tools = []
    for tool in mcp_client.list_available_tools():
        params = []
        for p in tool.parameters:
            param_dict = {"name": p.name, "type": p.type, "description": p.description, "required": p.required}
            if p.default is not None:
                param_dict["default"] = p.default
            if p.enum:
                param_dict["enum"] = p.enum
            params.append(param_dict)
        tools.append(McpToolInfo(
            name=tool.name,
            description=tool.description,
            side_effect=tool.side_effect,
            category=tool.category,
            parameters=params,
        ))
    return McpToolListResponse(tools=tools, server_id="all_enabled")


@router.post("/tools/call", response_model=McpToolCallResponse)
def call_mcp_tool(request: McpToolCallRequest) -> McpToolCallResponse:
    """Call an MCP tool. Side-effect tools require confirmed=True."""
    try:
        result = mcp_client.call_tool(
            tool_name=request.tool_name,
            arguments=request.arguments,
            confirmed=request.confirmed,
        )
        return McpToolCallResponse(
            success=result.success,
            data=result.data,
            error=result.error,
            requires_confirmation=result.requires_confirmation,
            preview=result.preview,
        )
    except Exception as error:
        logger.exception("MCP tool call failed")
        raise HTTPException(status_code=500, detail=f"Tool call failed: {error}") from error
