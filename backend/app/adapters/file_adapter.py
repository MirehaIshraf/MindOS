import shutil
from pathlib import Path


class FileAdapter:
    def create_folder(self, path: str) -> dict:
        target = Path(path).resolve()
        if target.exists():
            if target.is_dir():
                return {"status": "skipped", "message": "Folder already exists.", "path": str(target)}
            raise FileExistsError(f"Destination exists and is not a folder: {target}")
        target.mkdir(parents=True, exist_ok=False)
        return {"status": "created", "path": str(target)}

    def move_file(self, from_path: str, to_path: str) -> dict:
        source = Path(from_path).resolve()
        destination = Path(to_path).resolve()
        self._assert_file_destination(source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return {"status": "moved", "from_path": str(source), "to_path": str(destination)}

    def copy_file(self, from_path: str, to_path: str) -> dict:
        source = Path(from_path).resolve()
        destination = Path(to_path).resolve()
        self._assert_file_destination(source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return {"status": "copied", "from_path": str(source), "to_path": str(destination)}

    def rename_file(self, from_path: str, to_path: str) -> dict:
        source = Path(from_path).resolve()
        destination = Path(to_path).resolve()
        self._assert_file_destination(source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return {"status": "renamed", "from_path": str(source), "to_path": str(destination)}

    def remove_folder_if_empty(self, path: str) -> dict:
        target = Path(path).resolve()
        if not target.exists():
            return {"status": "skipped", "message": "Folder no longer exists.", "path": str(target)}
        target.rmdir()
        return {"status": "removed", "path": str(target)}

    def _assert_file_destination(self, source: Path, destination: Path) -> None:
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")
        if destination.exists():
            raise FileExistsError(f"Destination already exists: {destination}")


file_adapter = FileAdapter()
