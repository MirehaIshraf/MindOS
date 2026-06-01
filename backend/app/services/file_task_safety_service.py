from pathlib import Path

from app.schemas.file_tasks import FileOperation

ALLOWED_OPERATIONS = {"create_folder", "move_file", "copy_file", "rename_file"}
SYSTEM_PATH_MARKERS = [
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
]


class FileTaskSafetyService:
    def validate_root(self, root_path: str) -> tuple[Path, list[str]]:
        root = Path(root_path).expanduser().resolve()
        blocked: list[str] = []
        if not root.exists():
            blocked.append("Root path does not exist.")
        elif not root.is_dir():
            blocked.append("Root path must be a directory.")
        root_text = str(root).lower()
        if root.anchor and str(root) == root.anchor:
            blocked.append("Drive roots are not allowed.")
        if any(marker in root_text for marker in SYSTEM_PATH_MARKERS):
            blocked.append("System folders are not allowed.")
        try:
            home = Path.home().resolve()
            if root == home:
                blocked.append("User home root is not allowed. Choose a specific subfolder.")
        except Exception:
            pass
        return root, blocked

    def validate_plan(self, root_path: str, operations: list[FileOperation], max_operations: int = 500) -> dict:
        root, blocked = self.validate_root(root_path)
        warnings: list[str] = []
        if len(operations) > max_operations:
            blocked.append(f"Operation count exceeds limit of {max_operations}.")
        for index, operation in enumerate(operations[:max_operations], start=1):
            blocked.extend(self._validate_operation(root, operation, index))
        return {
            "blocked_reasons": dedupe(blocked),
            "warnings": dedupe(warnings),
            "status": "blocked" if blocked else "awaiting_confirmation",
        }

    def _validate_operation(self, root: Path, operation: FileOperation, index: int) -> list[str]:
        blocked: list[str] = []
        if operation.type not in ALLOWED_OPERATIONS:
            return [f"Operation {index}: forbidden operation {operation.type}."]
        if operation.type == "create_folder":
            target = self._resolve_path(operation.path)
            if target is None:
                return [f"Operation {index}: create_folder requires path."]
            blocked.extend(self._inside_root(root, target, index, "path"))
            if target.exists() and not target.is_dir():
                blocked.append(f"Operation {index}: destination exists and is not a folder.")
            return blocked

        source = self._resolve_path(operation.from_path)
        destination = self._resolve_path(operation.to_path)
        if source is None or destination is None:
            return [f"Operation {index}: {operation.type} requires from_path and to_path."]
        blocked.extend(self._inside_root(root, source, index, "from_path"))
        blocked.extend(self._inside_root(root, destination, index, "to_path"))
        if not source.exists():
            blocked.append(f"Operation {index}: source file does not exist.")
        elif not source.is_file():
            blocked.append(f"Operation {index}: source must be a file.")
        if destination.exists():
            blocked.append(f"Operation {index}: destination already exists; overwrite is not allowed.")
        parent = destination.parent
        blocked.extend(self._inside_root(root, parent, index, "destination parent"))
        if parent.exists() and not parent.is_dir():
            blocked.append(f"Operation {index}: destination parent is not a folder.")
        if is_hidden_or_system(source):
            blocked.append(f"Operation {index}: hidden/system files are skipped by default.")
        return blocked

    def _inside_root(self, root: Path, path: Path, index: int, label: str) -> list[str]:
        try:
            path.relative_to(root)
            return []
        except ValueError:
            return [f"Operation {index}: {label} is outside the selected root."]

    def _resolve_path(self, value: str | None) -> Path | None:
        if not value:
            return None
        return Path(value).expanduser().resolve()


def is_hidden_or_system(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    try:
        attrs = getattr(path.stat(), "st_file_attributes", 0)
        return bool(attrs & 0x2 or attrs & 0x4)
    except OSError:
        return False


def dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


file_task_safety_service = FileTaskSafetyService()
