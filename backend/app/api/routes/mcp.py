"""MCP API routes — server status, tool discovery, tool execution."""

from __future__ import annotations

import logging
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.integrations.mcp.client import mcp_client
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
from app.services.file_snapshot_service import PROTECTED_MARKERS, is_hidden, validate_root_path
from app.services.mcp_config_service import mcp_config_service
from app.services.mcp_file_watch_service import mcp_file_watch_service

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
            config=_config_for_response(info.server_id, info.config),
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
        config=_config_for_response(info.server_id, info.config),
    )


@router.get("/servers/{server_id}/config", response_model=McpServerConfigResponse)
def get_mcp_server_config(server_id: str) -> McpServerConfigResponse:
    """Get the configuration for an MCP server."""
    info = mcp_client.get_server_info(server_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found.")
    return McpServerConfigResponse(
        server_id=server_id,
        config=_config_for_response(server_id, info.config),
        configured=info.configured,
        message="" if info.configured else "Configuration required before enabling this server.",
    )


@router.post("/servers/{server_id}/config", response_model=McpServerConfigResponse)
def update_mcp_server_config(server_id: str, request: McpServerConfigRequest) -> McpServerConfigResponse:
    """Update the configuration for an MCP server."""
    info = mcp_client.get_server_info(server_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found.")

    # Pre-validate root_path for filesystem server
    if server_id == "filesystem":
        root_path = request.config.get("root_path", "")
        if root_path:
            try:
                root = validate_root_path(str(root_path))
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            request.config["root_path"] = str(root)
        persisted = mcp_config_service.save_filesystem_config(request.config)
        request.config = persisted

    ok = mcp_client.update_server_config(server_id, request.config)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update server configuration.")
    if server_id == "filesystem":
        mcp_file_watch_service.start_for_config()
        if request.config.get("index_readable_files", True) and request.config.get("root_path"):
            mcp_file_watch_service.schedule_index("config_saved")
    updated_info = mcp_client.get_server_info(server_id)
    return McpServerConfigResponse(
        server_id=server_id,
        config=_config_for_response(server_id, updated_info.config if updated_info else request.config),
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


@router.get("/servers/{server_id}/browse")
def browse_mcp_server_folder(server_id: str, path: str | None = None) -> dict[str, object]:
    if server_id != "filesystem":
        raise HTTPException(status_code=404, detail="Folder browsing is only available for File System MCP.")
    try:
        return _browse_folders(path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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


def _browse_folders(path: str | None) -> dict[str, object]:
    drives = _windows_drives()
    if not path:
        home = Path.home()
        current = home if home.exists() else None
    else:
        raw = path.strip()
        if raw.startswith("\\\\"):
            raise ValueError("Network folders are not supported yet.")
        current = Path(raw).expanduser().resolve()
    if current is None:
        return {"current_path": None, "parent_path": None, "drives": drives, "entries": []}
    if not current.exists() or not current.is_dir():
        raise ValueError("Folder path does not exist.")
    entries = []
    try:
        children = sorted(current.iterdir(), key=lambda item: item.name.lower())
    except (OSError, PermissionError) as error:
        raise ValueError(f"Could not open folder: {error}") from error
    for child in children:
        try:
            if not child.is_dir() or child.is_symlink() or is_hidden(child) or _is_protected(child):
                continue
            entries.append({"name": child.name, "path": str(child.resolve()), "is_dir": True})
        except (OSError, PermissionError):
            continue
    parent = current.parent if current.parent != current else None
    selectable = True
    selection_error = None
    try:
        validate_root_path(str(current))
    except ValueError as error:
        selectable = False
        selection_error = str(error)
    return {
        "current_path": str(current),
        "parent_path": str(parent) if parent else None,
        "drives": drives,
        "entries": entries,
        "selectable": selectable,
        "selection_error": selection_error,
    }


def _windows_drives() -> list[dict[str, str]]:
    drives: list[dict[str, str]] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            drives.append({"name": f"{letter}:\\", "path": str(root)})
    if drives:
        return drives
    root = Path("/")
    return [{"name": str(root), "path": str(root)}] if root.exists() else []


def _is_protected(path: Path) -> bool:
    text = str(path).lower()
    parts = {part.lower() for part in path.parts}
    return any(marker in parts or marker in text for marker in PROTECTED_MARKERS)


def _config_for_response(server_id: str, config: dict) -> dict:
    if server_id == "filesystem":
        persisted = mcp_config_service.get_filesystem_config()
        if persisted:
            return persisted
    return config
