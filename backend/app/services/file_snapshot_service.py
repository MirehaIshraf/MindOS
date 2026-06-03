from datetime import datetime, timezone
from pathlib import Path

from app.schemas.file_tasks import FileSnapshotItem, FileSnapshotResponse


PROTECTED_MARKERS = {
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
}


class FileSnapshotService:
    def scan_folder(
        self,
        root_path: str,
        max_depth: int = 2,
        max_files: int = 500,
        include_hidden: bool = False,
    ) -> FileSnapshotResponse:
        root = validate_root_path(root_path)
        max_depth = max(0, min(max_depth, 5))
        max_files = max(1, min(max_files, 1000))

        files: list[FileSnapshotItem] = []
        folders: list[FileSnapshotItem] = []
        warnings: list[str] = []
        state = {"truncated": False, "depth_warning": False}

        def add_warning(message: str) -> None:
            if message not in warnings:
                warnings.append(message)

        def walk(path: Path, depth: int) -> None:
            if len(files) >= max_files:
                state["truncated"] = True
                add_warning(f"Scan was limited to {max_files} files.")
                return
            if depth > max_depth:
                state["truncated"] = True
                if not state["depth_warning"]:
                    add_warning(f"Depth limit reached at {max_depth}; deeper folders skipped.")
                    state["depth_warning"] = True
                return
            try:
                entries = sorted(path.iterdir(), key=lambda item: (not safe_is_dir(item), item.name.lower()))
            except (OSError, PermissionError) as error:
                add_warning(f"Could not access {path}: {error}")
                return

            for entry in entries:
                if len(files) >= max_files:
                    state["truncated"] = True
                    add_warning(f"Scan was limited to {max_files} files.")
                    return
                try:
                    if entry.is_symlink():
                        add_warning(f"Skipped symlink: {entry}")
                        continue
                    hidden = is_hidden(entry)
                    if hidden and not include_hidden:
                        continue
                    if entry.is_dir():
                        folders.append(to_snapshot_item(root, entry, is_dir=True, hidden=hidden))
                        walk(entry, depth + 1)
                    elif entry.is_file():
                        files.append(to_snapshot_item(root, entry, is_dir=False, hidden=hidden))
                except (OSError, PermissionError) as error:
                    add_warning(f"Could not inspect {entry}: {error}")

        walk(root, 0)
        return FileSnapshotResponse(
            root_path=str(root),
            files=files,
            folders=folders,
            total_files=len(files),
            total_folders=len(folders),
            total_size_bytes=sum(item.size_bytes for item in files),
            max_depth=max_depth,
            max_files=max_files,
            truncated=state["truncated"],
            warnings=warnings,
        )

    def scan(self, root_path: str, max_depth: int = 2, max_files: int = 500, include_hidden: bool = False) -> FileSnapshotResponse:
        return self.scan_folder(root_path, max_depth=max_depth, max_files=max_files, include_hidden=include_hidden)


def validate_root_path(root_path: str) -> Path:
    raw_path = root_path.strip()
    if not raw_path:
        raise ValueError("Folder path is required.")
    if any(ord(char) < 32 for char in raw_path):
        raise ValueError("Folder path contains invalid characters.")
    if raw_path.startswith("\\\\"):
        raise ValueError("Network folders are not supported yet.")

    try:
        root = Path(raw_path).expanduser().resolve()
    except (OSError, RuntimeError) as error:
        raise ValueError(f"Folder path is invalid: {error}") from error

    if not root.exists():
        raise ValueError("Folder path does not exist.")
    if not root.is_dir():
        raise ValueError("Folder path must be a directory.")
    if root.anchor and str(root) == root.anchor:
        raise ValueError("This folder is protected and cannot be scanned by MindOS.")

    root_text = str(root).lower()
    parts = {part.lower() for part in root.parts}
    if any(marker in parts or marker in root_text for marker in PROTECTED_MARKERS):
        raise ValueError("This folder is protected and cannot be scanned by MindOS.")

    try:
        home = Path.home().resolve()
        if root == home:
            raise ValueError("Choose a specific subfolder instead of your home folder.")
    except RuntimeError:
        pass

    return root


def to_snapshot_item(root: Path, path: Path, *, is_dir: bool, hidden: bool) -> FileSnapshotItem:
    resolved = path.resolve()
    stat = path.stat()
    return FileSnapshotItem(
        name=path.name,
        path=str(resolved),
        relative_path=str(resolved.relative_to(root)),
        extension="" if is_dir else path.suffix.lower(),
        size_bytes=0 if is_dir else int(stat.st_size),
        modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
        is_dir=is_dir,
        is_hidden=hidden,
    )


def safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    try:
        attrs = getattr(path.stat(), "st_file_attributes", 0)
        return bool(attrs & 0x2 or attrs & 0x4)
    except OSError:
        return False


file_snapshot_service = FileSnapshotService()
