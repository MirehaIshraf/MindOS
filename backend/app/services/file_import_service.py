from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus
from app.repositories.base import EventRepository
from app.schemas.connectors import FileImportRequest, FileImportResult, FilePreviewRequest, FilePreviewResult
from app.services.relationship_service import relationship_service

DEFAULT_ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".dart",
    ".scala",
    ".sql",
    ".html",
    ".css",
    ".scss",
}

DEFAULT_ALLOWED_FILENAMES = {
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
}

SKIPPED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
    ".next",
    "coverage",
}

SENSITIVE_MARKERS = {
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "AWS_SECRET_ACCESS_KEY",
    "SECRET_KEY=",
    "PRIVATE_KEY=",
}


class FileImportService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()

    def preview_folder(self, request: FilePreviewRequest) -> FilePreviewResult:
        folder = self._validate_folder(request.folder_path)
        allowed = self._allowed_extensions(request.allowed_extensions)
        candidates, skipped = self._collect_candidates(
            folder=folder,
            recursive=request.recursive,
            max_files=request.max_files,
            max_file_size_kb=request.max_file_size_kb,
            allowed_extensions=allowed,
        )
        preview_files = [self._file_info(path) for path in candidates[: request.max_files]]
        return FilePreviewResult(total_candidates=len(candidates), preview_files=preview_files, skipped=skipped)

    def import_folder(self, request: FileImportRequest) -> FileImportResult:
        folder = self._validate_folder(request.folder_path)
        allowed = self._allowed_extensions(request.allowed_extensions)
        candidates, skipped = self._collect_candidates(
            folder=folder,
            recursive=request.recursive,
            max_files=request.max_files,
            max_file_size_kb=request.max_file_size_kb,
            allowed_extensions=allowed,
        )

        imported_ids: list[str] = []
        failed: list[dict] = []
        existing = self._existing_file_imports()

        for path in candidates[: request.max_files]:
            try:
                content = self._read_text_file(path=path, max_file_size_kb=request.max_file_size_kb)
                if self._has_sensitive_content(content):
                    skipped.append(self._skip(path, "sensitive_content_detected"))
                    continue

                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                full_path = str(path.resolve())
                prior_hashes = existing.get(full_path, set())
                if content_hash in prior_hashes:
                    skipped.append(self._skip(path, "already_imported"))
                    continue

                event_type = "file_modified_imported" if prior_hashes else "file_imported"
                event = self._event_repository.create_event(
                    {
                        "source": "file_system",
                        "type": event_type,
                        "title": path.name,
                        "content": content,
                        "metadata": {
                            "path": full_path,
                            "name": path.name,
                            "extension": self._extension_for(path),
                            "size_kb": self._size_kb(path),
                            "content_hash": content_hash,
                            "import_method": "manual_folder_import",
                            "recursive": request.recursive,
                        },
                        "timestamp": datetime.now(timezone.utc),
                        "embedding_status": EmbeddingStatus.not_required,
                    }
                )
                imported_ids.append(event.id)
                existing.setdefault(full_path, set()).add(content_hash)
                relationship_service.detect_relationships_for_event(event)
            except Exception as error:
                failed.append({"path": str(path), "reason": str(error)})

        return FileImportResult(
            imported_count=len(imported_ids),
            skipped_count=len(skipped),
            failed_count=len(failed),
            events_created=imported_ids,
            skipped=skipped,
            failed=failed,
            message=f"Imported {len(imported_ids)} files into MindOS memory.",
        )

    def _validate_folder(self, folder_path: str) -> Path:
        folder = Path(folder_path).expanduser()
        if not folder.exists():
            raise ValueError("Folder path does not exist.")
        if not folder.is_dir():
            raise ValueError("Folder path must be a directory.")
        return folder

    def _collect_candidates(
        self,
        *,
        folder: Path,
        recursive: bool,
        max_files: int,
        max_file_size_kb: int,
        allowed_extensions: set[str],
    ) -> tuple[list[Path], list[dict]]:
        candidates: list[Path] = []
        skipped: list[dict] = []
        iterator = folder.rglob("*") if recursive else folder.glob("*")

        for path in iterator:
            if len(candidates) >= max_files:
                break
            if self._should_skip_path(path):
                if path.is_file():
                    skipped.append(self._skip(path, "skipped_path"))
                continue
            if not path.is_file():
                continue

            skip_reason = self._skip_reason(path, max_file_size_kb=max_file_size_kb, allowed_extensions=allowed_extensions)
            if skip_reason:
                skipped.append(self._skip(path, skip_reason))
                continue
            candidates.append(path)

        return candidates, skipped

    def _skip_reason(self, path: Path, *, max_file_size_kb: int, allowed_extensions: set[str]) -> str | None:
        if path.name == ".env":
            return "sensitive_file"
        if path.name.startswith(".") and path.name not in DEFAULT_ALLOWED_FILENAMES:
            return "hidden_file"
        if not self._is_allowed_file(path, allowed_extensions):
            return "unsupported_extension"
        if self._size_kb(path) > max_file_size_kb:
            return "file_too_large"
        if self._appears_binary(path):
            return "binary_file"
        return None

    def _read_text_file(self, *, path: Path, max_file_size_kb: int) -> str:
        max_bytes = max_file_size_kb * 1024
        with path.open("rb") as handle:
            data = handle.read(max_bytes)
        if data.count(b"\x00") > 0:
            raise ValueError("binary_file")
        return data.decode("utf-8", errors="replace")

    def _appears_binary(self, path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                sample = handle.read(4096)
            return sample.count(b"\x00") > 0
        except OSError:
            return True

    def _has_sensitive_content(self, content: str) -> bool:
        return any(marker in content for marker in SENSITIVE_MARKERS)

    def _should_skip_path(self, path: Path) -> bool:
        parts = path.parts
        for index, part in enumerate(parts):
            if part in SKIPPED_DIRS:
                return True
            if part == "archive" and index > 0 and parts[index - 1] == "logs":
                return True
        return False

    def _is_allowed_file(self, path: Path, allowed_extensions: set[str]) -> bool:
        return path.name in DEFAULT_ALLOWED_FILENAMES or self._extension_for(path) in allowed_extensions

    def _allowed_extensions(self, extensions: list[str] | None) -> set[str]:
        if not extensions:
            return DEFAULT_ALLOWED_EXTENSIONS
        return {extension if extension.startswith(".") else f".{extension}" for extension in extensions}

    def _existing_file_imports(self) -> dict[str, set[str]]:
        existing: dict[str, set[str]] = {}
        for event in self._event_repository.list_all_events(include_hidden=True):
            if event.type not in {"file_imported", "file_modified_imported"}:
                continue
            path = event.metadata.get("path")
            content_hash = event.metadata.get("content_hash")
            if isinstance(path, str) and isinstance(content_hash, str):
                existing.setdefault(path, set()).add(content_hash)
        return existing

    def _file_info(self, path: Path) -> dict:
        return {
            "path": str(path.resolve()),
            "name": path.name,
            "extension": self._extension_for(path),
            "size_kb": self._size_kb(path),
        }

    def _skip(self, path: Path, reason: str) -> dict:
        return {"path": str(path), "name": path.name, "reason": reason}

    def _size_kb(self, path: Path) -> float:
        return round(path.stat().st_size / 1024, 2)

    def _extension_for(self, path: Path) -> str:
        if path.name in DEFAULT_ALLOWED_FILENAMES:
            return path.name
        return path.suffix.lower()
