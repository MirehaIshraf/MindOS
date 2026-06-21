"""MCP File System Server — exposes safe file organization tools.

This server wraps MindOS's existing file task services behind the MCP protocol.
Every tool call is validated independently — the LLM caller is never trusted.

Safety rules enforced at the server level:
- No delete, overwrite, shell commands, or file content reading
- All paths must stay inside user-allowed roots
- Side-effect operations require confirmation
- Hidden/system files are skipped
- Max depth, max files, and max operations limits are enforced
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.adapters.file_adapter import file_adapter
from app.integrations.mcp.protocol import (
    McpToolCallResult,
    McpToolDefinition,
    McpToolParameter,
)
from app.schemas.file_tasks import FileOperation
from app.services.file_snapshot_service import file_snapshot_service
from app.services.file_task_safety_service import file_task_safety_service

# ---------------------------------------------------------------------------
# TYPE_FOLDERS — same as FileTaskPlannerService
# ---------------------------------------------------------------------------

TYPE_FOLDERS: dict[str, set[str]] = {
    "PDFs": {".pdf"},
    "Images": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "Audio": {".mp3", ".wav", ".m4a", ".flac", ".aac"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm"},
    "Code": {".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".xml", ".yml", ".yaml"},
    "Documents": {".doc", ".docx", ".txt", ".md", ".rtf"},
    "Spreadsheets": {".xls", ".xlsx", ".csv"},
    "Presentations": {".ppt", ".pptx"},
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

FILE_SYSTEM_TOOLS: list[McpToolDefinition] = [
    McpToolDefinition(
        name="fs.scan_folder",
        description="Scan a folder and return metadata for all files (name, extension, size, modified date). No file contents are read. Returns category counts.",
        parameters=[
            McpToolParameter(name="root_path", type="string", description="Absolute path to the folder to scan."),
            McpToolParameter(name="max_depth", type="integer", description="Maximum folder depth to scan (1-5).", required=False, default=2),
            McpToolParameter(name="max_files", type="integer", description="Maximum number of files to return (1-1000).", required=False, default=500),
            McpToolParameter(name="include_hidden", type="boolean", description="Include hidden files in the scan.", required=False, default=False),
        ],
        side_effect=False,
        category="filesystem",
    ),
    McpToolDefinition(
        name="fs.list_categories",
        description="List the file type categories and their associated extensions used for organizing files by type.",
        parameters=[],
        side_effect=False,
        category="filesystem",
    ),
    McpToolDefinition(
        name="fs.organize_plan",
        description="Generate a file organization plan for a scanned folder. Groups files by type into category folders. Returns a preview of planned operations (create_folder + move_file) without executing them.",
        parameters=[
            McpToolParameter(name="root_path", type="string", description="Absolute path to the folder to organize."),
            McpToolParameter(name="instruction", type="string", description="How to organize the folder, e.g. 'Organize by file type' or 'Move PDFs into PDFs folder'."),
            McpToolParameter(name="include_others", type="boolean", description="Include unknown file types in an 'Other' folder.", required=False, default=False),
            McpToolParameter(name="max_depth", type="integer", description="Maximum folder depth to scan.", required=False, default=2),
            McpToolParameter(name="max_files", type="integer", description="Maximum number of files to scan.", required=False, default=500),
        ],
        side_effect=False,
        category="filesystem",
    ),
    McpToolDefinition(
        name="fs.create_folder",
        description="Create a single folder inside an allowed root. The folder must not already exist. The path must be inside a validated root directory.",
        parameters=[
            McpToolParameter(name="root_path", type="string", description="The allowed root directory."),
            McpToolParameter(name="folder_path", type="string", description="Relative or absolute path of the folder to create. Must be inside root_path."),
        ],
        side_effect=True,
        category="filesystem",
    ),
    McpToolDefinition(
        name="fs.move_file",
        description="Move a file from one location to another inside an allowed root. Destination must not already exist. Source must be a file. No overwrite allowed.",
        parameters=[
            McpToolParameter(name="root_path", type="string", description="The allowed root directory."),
            McpToolParameter(name="from_path", type="string", description="Current file path. Must be inside root_path."),
            McpToolParameter(name="to_path", type="string", description="Destination file path. Must be inside root_path. Must not already exist."),
        ],
        side_effect=True,
        category="filesystem",
    ),
    McpToolDefinition(
        name="fs.file_exists",
        description="Check whether a file or folder exists at the given path. Returns existence status and whether it is a file or directory.",
        parameters=[
            McpToolParameter(name="path", type="string", description="Absolute path to check."),
        ],
        side_effect=False,
        category="filesystem",
    ),
    McpToolDefinition(
        name="fs.folder_summary",
        description="Get a quick summary of a folder: total files, total size, category breakdown. No file contents are read.",
        parameters=[
            McpToolParameter(name="root_path", type="string", description="Absolute path to the folder."),
            McpToolParameter(name="max_depth", type="integer", description="Maximum folder depth.", required=False, default=2),
        ],
        side_effect=False,
        category="filesystem",
    ),
]


# ---------------------------------------------------------------------------
# File System MCP Server
# ---------------------------------------------------------------------------

class FileSystemMcpServer:
    """MCP Server for local file system operations.

    All safety rules from FileTaskSafetyService are enforced here.
    The LLM caller cannot bypass these validations.

    Configuration:
        root_path (required): The allowed root directory for all operations.
            The LLM can only operate inside this directory recursively.
            Must be set before the server can be used.
    """

    SERVER_ID = "filesystem"
    SERVER_NAME = "File System MCP"
    SERVER_DESCRIPTION = "Local file system tools for scanning, organizing, and managing files and folders."
    REQUIRED_CONFIG_KEYS = ["root_path"]

    def __init__(self) -> None:
        self._root_path: str | None = None

    @property
    def root_path(self) -> str | None:
        return self._root_path

    def apply_config(self, config: dict[str, Any]) -> None:
        """Apply configuration from the MCP client."""
        root = config.get("root_path", "")
        if root:
            from pathlib import Path
            resolved = Path(root).resolve()
            if resolved.is_dir():
                self._root_path = str(resolved)
            else:
                self._root_path = None
        else:
            self._root_path = None

    def _ensure_configured(self) -> McpToolCallResult | None:
        """Return an error result if the server is not configured, else None."""
        if not self._root_path:
            return McpToolCallResult(
                success=False,
                error="File System MCP server is not configured. Set a root directory in the Connectors page first.",
            )
        return None

    def _resolve_root(self, args: dict[str, Any]) -> tuple[str, McpToolCallResult | None]:
        """Resolve the root path from args or config.

        Priority:
        1. If args contains root_path AND it's an absolute path → use it
           (if configured root exists, validate the args path is within it)
        2. If configured root_path exists → use it
        3. Error

        Returns (root_path, error_result). If error_result is set, return it.
        """
        root_arg = args.get("root_path", "")
        root_arg_is_absolute = bool(root_arg) and Path(root_arg).is_absolute()

        if root_arg_is_absolute:
            # User explicitly provided a path — if configured root exists, enforce it as a boundary
            if self._root_path:
                try:
                    Path(root_arg).resolve().relative_to(Path(self._root_path).resolve())
                    # args path is inside configured root → allow it
                    return root_arg, None
                except ValueError:
                    # args path is OUTSIDE configured root → block it
                    return "", McpToolCallResult(
                        success=False,
                        error=f"Path '{root_arg}' is outside the configured root directory '{self._root_path}'. "
                        f"You can only access files inside the configured root.",
                    )
            # No configured root — use the explicit path
            return root_arg, None

        # No explicit path in args — use configured root
        if self._root_path:
            return self._root_path, None

        return "", McpToolCallResult(
            success=False,
            error="No root directory configured. Set a root directory in the Connectors page, or provide root_path in the tool call.",
        )

    def list_tools(self) -> list[McpToolDefinition]:
        return list(FILE_SYSTEM_TOOLS)

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolCallResult:
        handler = {
            "fs.scan_folder": self._scan_folder,
            "fs.list_categories": self._list_categories,
            "fs.organize_plan": self._organize_plan,
            "fs.create_folder": self._create_folder,
            "fs.move_file": self._move_file,
            "fs.file_exists": self._file_exists,
            "fs.folder_summary": self._folder_summary,
        }.get(tool_name)
        if handler is None:
            return McpToolCallResult(success=False, error=f"Unknown tool: {tool_name}")
        try:
            return handler(arguments)
        except Exception as error:
            return McpToolCallResult(success=False, error=str(error))

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _scan_folder(self, args: dict[str, Any]) -> McpToolCallResult:
        root_path, err = self._resolve_root(args)
        if err:
            return err
        max_depth = int(args.get("max_depth", 2))
        max_files = int(args.get("max_files", 500))
        include_hidden = bool(args.get("include_hidden", False))

        root, blocked = file_task_safety_service.validate_root(root_path)
        if blocked:
            return McpToolCallResult(success=False, error="; ".join(blocked))

        snapshot = file_snapshot_service.scan(str(root), max_depth, max_files, include_hidden)
        category_counts: dict[str, int] = {}
        for item in snapshot.files:
            category = self._category_for_extension(item.extension)
            category_counts[category] = category_counts.get(category, 0) + 1

        return McpToolCallResult(
            success=True,
            data={
                "root_path": snapshot.root_path,
                "total_files": snapshot.total_files,
                "total_folders": snapshot.total_folders,
                "total_size_bytes": snapshot.total_size_bytes,
                "category_counts": category_counts,
                "files": [
                    {
                        "name": f.name,
                        "relative_path": f.relative_path,
                        "extension": f.extension,
                        "size_bytes": f.size_bytes,
                        "modified_at": f.modified_at.isoformat() if isinstance(f.modified_at, datetime) else str(f.modified_at),
                        "category": self._category_for_extension(f.extension),
                    }
                    for f in snapshot.files
                ],
                "folders": [f.name for f in snapshot.folders],
                "warnings": snapshot.warnings,
                "truncated": snapshot.truncated,
            },
        )

    def _list_categories(self, _args: dict[str, Any]) -> McpToolCallResult:
        categories = {name: sorted(extensions) for name, extensions in TYPE_FOLDERS.items()}
        return McpToolCallResult(
            success=True,
            data={"categories": categories},
        )

    def _organize_plan(self, args: dict[str, Any]) -> McpToolCallResult:
        root_path, err = self._resolve_root(args)
        if err:
            return err
        instruction = args.get("instruction", "Organize by file type")
        include_others = bool(args.get("include_others", False))
        max_depth = int(args.get("max_depth", 2))
        max_files = int(args.get("max_files", 500))

        root, blocked = file_task_safety_service.validate_root(root_path)
        if blocked:
            return McpToolCallResult(success=False, error="; ".join(blocked))

        snapshot = file_snapshot_service.scan(str(root), max_depth, max_files, False)
        operations: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        destination_folders: set[str] = set()
        category_counts: dict[str, int] = {}

        for item in snapshot.files:
            category = self._category_for_extension(item.extension)
            if category == "Other" and not include_others:
                skipped.append({"path": item.relative_path, "reason": "Unknown file type."})
                continue
            category_counts[category] = category_counts.get(category, 0) + 1
            source = Path(item.path).resolve()
            dest_folder = root / category
            dest = dest_folder / source.name
            if source.parent.resolve() == dest_folder.resolve():
                skipped.append({"path": item.relative_path, "reason": "Already organized."})
                continue
            if dest.exists():
                skipped.append({"path": item.relative_path, "reason": "Destination already exists."})
                continue
            destination_folders.add(category)
            operations.append({
                "type": "move_file",
                "from_path": str(source),
                "to_path": str(dest),
                "relative_from": str(source.relative_to(root)),
                "relative_to": str(dest.relative_to(root)),
                "reason": f"{self._category_singular(category)} file grouped under {category}.",
            })

        create_ops: list[dict[str, Any]] = []
        for category in sorted(destination_folders):
            folder_path = root / category
            if not folder_path.exists():
                create_ops.append({
                    "type": "create_folder",
                    "path": str(folder_path),
                    "relative_to": str(folder_path.relative_to(root)),
                    "reason": f"Create {category} folder for organized files.",
                })

        all_ops = []
        for i, op in enumerate(create_ops + operations, 1):
            op["id"] = f"op_{i:03d}"
            op["status"] = "planned"
            all_ops.append(op)

        validation = file_task_safety_service.validate_plan(
            str(root), [FileOperation(**op) for op in all_ops]
        )
        if validation["blocked_reasons"]:
            return McpToolCallResult(
                success=False,
                error="Plan validation failed: " + "; ".join(validation["blocked_reasons"]),
                data={"blocked_reasons": validation["blocked_reasons"]},
            )

        plan_id = str(uuid4())
        return McpToolCallResult(
            success=True,
            data={
                "plan_id": plan_id,
                "root_path": str(root),
                "instruction": instruction,
                "total_operations": len(all_ops),
                "create_folder_count": len(create_ops),
                "move_file_count": len(operations),
                "category_counts": category_counts,
                "operations": all_ops,
                "skipped": skipped,
                "warnings": snapshot.warnings + validation.get("warnings", []),
                "requires_confirmation": True,
            },
            requires_confirmation=bool(all_ops),
            preview={
                "plan_id": plan_id,
                "summary": f"Organize {len(operations)} files into {len(destination_folders)} folders by type.",
                "total_operations": len(all_ops),
                "operations": all_ops,
            },
        )

    def _create_folder(self, args: dict[str, Any]) -> McpToolCallResult:
        root_path, err = self._resolve_root(args)
        if err:
            return err
        folder_path = args.get("folder_path", "")

        root, blocked = file_task_safety_service.validate_root(root_path)
        if blocked:
            return McpToolCallResult(success=False, error="Root validation failed: " + "; ".join(blocked))

        target = Path(folder_path).resolve() if Path(folder_path).is_absolute() else (root / folder_path).resolve()

        # Must be inside root
        try:
            target.relative_to(root)
        except ValueError:
            return McpToolCallResult(success=False, error="Folder path is outside the allowed root directory.")

        if target.exists():
            if target.is_dir():
                return McpToolCallResult(success=True, data={"status": "skipped", "message": "Folder already exists.", "path": str(target)})
            return McpToolCallResult(success=False, error="A file exists at the target path.")

        result = file_adapter.create_folder(str(target))
        return McpToolCallResult(
            success=True,
            data=result,
            requires_confirmation=False,  # Confirmation handled by router before this is called
        )

    def _move_file(self, args: dict[str, Any]) -> McpToolCallResult:
        root_path, err = self._resolve_root(args)
        if err:
            return err
        from_path = args.get("from_path", "")
        to_path = args.get("to_path", "")

        root, blocked = file_task_safety_service.validate_root(root_path)
        if blocked:
            return McpToolCallResult(success=False, error="Root validation failed: " + "; ".join(blocked))

        source = Path(from_path).resolve()
        destination = Path(to_path).resolve()

        # Both must be inside root
        try:
            source.relative_to(root)
            destination.relative_to(root)
        except ValueError:
            return McpToolCallResult(success=False, error="Source or destination is outside the allowed root directory.")

        # Source must exist and be a file
        if not source.exists():
            return McpToolCallResult(success=False, error=f"Source file does not exist: {source}")
        if not source.is_file():
            return McpToolCallResult(success=False, error=f"Source is not a file: {source}")

        # Destination must not exist
        if destination.exists():
            return McpToolCallResult(success=False, error=f"Destination already exists — overwrite is not allowed: {destination}")

        result = file_adapter.move_file(str(source), str(destination))
        return McpToolCallResult(
            success=True,
            data=result,
            requires_confirmation=False,  # Confirmation handled by router before this is called
        )

    def _file_exists(self, args: dict[str, Any]) -> McpToolCallResult:
        # If root_path is configured, validate the path is inside it
        if self._root_path:
            path = args.get("path", "")
            target = Path(path).resolve()
            root_resolved = Path(self._root_path).resolve()
            try:
                target.relative_to(root_resolved)
            except ValueError:
                return McpToolCallResult(success=False, error="Path is outside the configured root directory.")
        else:
            path = args.get("path", "")
            target = Path(path).resolve()

        if not target.exists():
            return McpToolCallResult(success=True, data={"exists": False, "path": str(target)})
        return McpToolCallResult(
            success=True,
            data={"exists": True, "path": str(target), "is_file": target.is_file(), "is_dir": target.is_dir()},
        )

    def _folder_summary(self, args: dict[str, Any]) -> McpToolCallResult:
        root_path, err = self._resolve_root(args)
        if err:
            return err
        max_depth = int(args.get("max_depth", 2))

        root, blocked = file_task_safety_service.validate_root(root_path)
        if blocked:
            return McpToolCallResult(success=False, error="; ".join(blocked))

        snapshot = file_snapshot_service.scan(str(root), max_depth, 1000, False)
        category_counts: dict[str, int] = {}
        for item in snapshot.files:
            category = self._category_for_extension(item.extension)
            category_counts[category] = category_counts.get(category, 0) + 1

        return McpToolCallResult(
            success=True,
            data={
                "root_path": snapshot.root_path,
                "total_files": snapshot.total_files,
                "total_folders": snapshot.total_folders,
                "total_size_bytes": snapshot.total_size_bytes,
                "category_counts": category_counts,
                "warnings": snapshot.warnings,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _category_for_extension(extension: str) -> str:
        ext = extension.lower()
        for folder, extensions in TYPE_FOLDERS.items():
            if ext in extensions:
                return folder
        return "Other"

    @staticmethod
    def _category_singular(category: str) -> str:
        if category == "PDFs":
            return "PDF"
        if category.endswith("s"):
            return category[:-1]
        return category


file_system_mcp_server = FileSystemMcpServer()
