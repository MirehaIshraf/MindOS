from pathlib import Path
from datetime import datetime, timezone

from app.schemas.file_tasks import FileSnapshotItem, FileSnapshotResponse


class FileSnapshotService:
    def scan(self, root_path: str, max_depth: int = 2, max_files: int = 500) -> FileSnapshotResponse:
        root = Path(root_path).expanduser().resolve()
        warnings: list[str] = []
        if not root.exists():
            raise ValueError("Root path does not exist.")
        if not root.is_dir():
            raise ValueError("Root path must be a directory.")

        max_depth = max(0, min(max_depth, 5))
        max_files = max(1, min(max_files, 1000))
        files: list[FileSnapshotItem] = []
        folders: list[FileSnapshotItem] = []

        def walk(path: Path, depth: int) -> None:
            if len(files) >= max_files:
                warnings.append(f"File limit reached at {max_files}; scan truncated.")
                return
            if depth > max_depth:
                warnings.append(f"Depth limit reached at {max_depth}; deeper folders skipped.")
                return
            try:
                entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            except OSError as error:
                warnings.append(f"Could not access {path}: {error}")
                return
            for entry in entries:
                if entry.is_symlink():
                    warnings.append(f"Skipped symlink: {entry}")
                    continue
                hidden = is_hidden(entry)
                try:
                    if entry.is_dir():
                        folders.append(to_snapshot_item(root, entry, is_dir=True, hidden=hidden))
                        if not hidden:
                            walk(entry, depth + 1)
                    elif entry.is_file():
                        if hidden:
                            continue
                        files.append(to_snapshot_item(root, entry, is_dir=False, hidden=hidden))
                        if len(files) >= max_files:
                            warnings.append(f"File limit reached at {max_files}; scan truncated.")
                            return
                except OSError as error:
                    warnings.append(f"Could not inspect {entry}: {error}")

        walk(root, 0)
        return FileSnapshotResponse(
            root_path=str(root),
            files=files,
            folders=folders,
            total_files=len(files),
            total_folders=len(folders),
            warnings=dedupe(warnings),
        )


def to_snapshot_item(root: Path, path: Path, *, is_dir: bool, hidden: bool) -> FileSnapshotItem:
    stat = path.stat()
    return FileSnapshotItem(
        name=path.name,
        path=str(path.resolve()),
        relative_path=str(path.resolve().relative_to(root)),
        extension="" if is_dir else path.suffix.lower(),
        size_bytes=0 if is_dir else int(stat.st_size),
        modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
        is_dir=is_dir,
        is_hidden=hidden,
    )


def is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    attrs = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attrs & 0x2 or attrs & 0x4)


def dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


file_snapshot_service = FileSnapshotService()
