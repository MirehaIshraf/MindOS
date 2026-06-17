from __future__ import annotations

import fnmatch
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.dependencies import get_connector_source_repository, get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.domain.models import ConnectorSource
from app.repositories.base import ConnectorSourceRepository, EventRepository
from app.schemas.file_index import (
    DEFAULT_FILE_INDEX_EXTENSIONS,
    FileIndexRunResult,
    IndexedFileAttachmentReference,
    IndexedFileSearchMatch,
    IndexedFileSearchRequest,
    IndexedFileSearchResponse,
    ResolveIndexedAttachmentsRequest,
    ResolveIndexedAttachmentsResponse,
    ResolvedIndexedAttachment,
)
from app.schemas.file_tasks import DocumentSummaryInputFile, DocumentSummarySkippedFile
from app.services.file_snapshot_service import is_hidden, validate_root_path


BLOCKED_FILE_INDEX_EXTENSIONS = {
    ".7z",
    ".bat",
    ".cmd",
    ".db",
    ".dll",
    ".env",
    ".exe",
    ".key",
    ".pem",
    ".ps1",
    ".rar",
    ".sh",
    ".sqlite",
    ".zip",
}
BLOCKED_ATTACHMENT_EXTENSIONS = BLOCKED_FILE_INDEX_EXTENSIONS | {".zip", ".rar", ".7z"}
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
BLOCKED_NAMES = {".env", ".npmrc", ".pypirc"}
DEFAULT_EXCLUDE_PATTERNS = ["node_modules", ".git", "dist", "build", "__pycache__", "**/__pycache__/**"]
MAX_EXTRACTED_CHARS_PER_FILE = 30_000
MAX_TOTAL_CHARS_PER_RUN = 1_000_000
READABLE_CONTENT_EXTENSIONS = {
    ".txt",
    ".md",
    ".log",
    ".json",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".pdf",
    ".docx",
    ".py",
    ".java",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".sql",
}


class FileIndexService:
    def __init__(
        self,
        events: EventRepository | None = None,
        sources: ConnectorSourceRepository | None = None,
    ) -> None:
        self._events = events or get_event_repository()
        self._sources = sources or get_connector_source_repository()

    def index_source(self, source_id: str) -> FileIndexRunResult:
        source = self._sources.get_source(source_id)
        if source is None:
            raise KeyError("Saved source not found.")
        if source.connector_type != "file_system":
            raise ValueError("Only File System sources can be indexed.")
        if not source.enabled:
            raise ValueError("This folder source is disabled.")

        config = self._normalized_config(source.config)
        if not bool(config["indexing_enabled"]):
            raise ValueError("Indexing is disabled for this folder source.")

        started_at = datetime.now(timezone.utc)
        root = validate_root_path(source.path)
        root_hash = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        state: dict[str, Any] = {
            "file_count": 0,
            "inventory_count": 0,
            "indexed_count": 0,
            "content_failed_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "failed_count": 0,
            "missing_count": 0,
            "total_chars": 0,
            "warnings": [],
            "skipped": [],
            "failed": [],
            "event_ids": [],
            "seen_dedupe_keys": set(),
            "seen_inventory_keys": set(),
            "inventory_records": {},
        }

        for path in self._iter_files(root, config, state):
            relative_path = str(path.resolve().relative_to(root))
            dedupe_key = f"{source.id}:{relative_path}"
            inventory = self._inventory_record(
                source=source,
                root_hash=root_hash,
                path=path,
                relative_path=relative_path,
                content_index_status="pending",
            )
            state["seen_inventory_keys"].add(dedupe_key)
            state["inventory_records"][dedupe_key] = inventory
            state["inventory_count"] += 1
            if state["total_chars"] >= MAX_TOTAL_CHARS_PER_RUN:
                inventory.update(
                    {
                        "content_index_status": "skipped",
                        "content_index_error": "Indexing run text limit reached.",
                        "content_event_id": None,
                    }
                )
                state["inventory_records"][dedupe_key] = inventory
                self._warn(state, "Indexing run text limit reached; remaining files were kept in inventory only.")
                continue
            try:
                result = self._index_file(source, root, root_hash, path, relative_path, config)
                state["seen_dedupe_keys"].add(result["dedupe_key"])
                inventory.update(
                    {
                        "content_index_status": result.get("content_index_status", "indexed"),
                        "content_index_error": result.get("content_index_error"),
                        "content_event_id": result.get("event_id"),
                        "indexed_text_chars": int(result.get("indexed_text_chars") or 0),
                    }
                )
                state["inventory_records"][dedupe_key] = inventory
                state["total_chars"] += int(result.get("indexed_text_chars") or 0)
                if result.get("event_id"):
                    state["event_ids"].append(result["event_id"])
                if result.get("content_index_status") == "indexed":
                    state["indexed_count"] += 1
                if result["updated"]:
                    state["updated_count"] += 1
                if result["unchanged"]:
                    state["unchanged_count"] += 1
            except Exception as error:
                state["failed_count"] += 1
                state["content_failed_count"] += 1
                inventory.update({"content_index_status": "failed", "content_index_error": str(error), "content_event_id": None})
                state["inventory_records"][dedupe_key] = inventory
                state["failed"].append({"relative_path": relative_path, "reason": str(error)})

        completed_at = datetime.now(timezone.utc)
        event_missing_count = self._mark_missing_files(source.id, state["seen_dedupe_keys"])
        inventory_records, inventory_missing_count = self._merge_inventory_records(source, state["inventory_records"], state["seen_inventory_keys"])
        state["missing_count"] = max(event_missing_count, inventory_missing_count)
        skipped_count = len(state["skipped"])
        result = FileIndexRunResult(
            source_id=source.id,
            root_path=str(root),
            file_count=state["file_count"],
            inventory_count=state["inventory_count"],
            indexed_count=state["indexed_count"],
            content_failed_count=state["content_failed_count"],
            skipped_count=skipped_count,
            updated_count=state["updated_count"],
            unchanged_count=state["unchanged_count"],
            failed_count=state["failed_count"],
            missing_count=state["missing_count"],
            warnings=state["warnings"],
            skipped=state["skipped"][:100],
            failed=state["failed"][:100],
            event_ids=state["event_ids"],
            started_at=started_at,
            completed_at=completed_at,
            message=f"Inventoried {state['inventory_count']} file(s), content-indexed {state['indexed_count']}, failed {state['content_failed_count']}, skipped {skipped_count}, marked {state['missing_count']} missing.",
        )
        self._update_source_index_metadata(source, result, inventory_records)
        return result

    def search(self, request: IndexedFileSearchRequest) -> IndexedFileSearchResponse:
        query = request.query.strip().lower()
        terms = [term for term in query.replace("-", " ").split() if term]
        extensions = {extension.lower() if extension.startswith(".") else f".{extension.lower()}" for extension in request.extensions}
        matches_by_key: dict[str, IndexedFileSearchMatch] = {}
        source_cache: dict[str, ConnectorSource | None] = {}

        for source in self._sources.list_sources(connector_type="file_system"):
            if not self._source_allowed_for_search(source, request):
                continue
            for record in self._inventory_records(source):
                if record.get("missing") is True:
                    continue
                extension = str(record.get("extension") or "").lower()
                if extensions and extension not in extensions:
                    continue
                if request.attachable_only and record.get("is_attachable") is not True:
                    continue
                readable = str(record.get("content_index_status") or "") == "indexed"
                if request.readable_only and not readable:
                    continue
                file_name = str(record.get("file_name") or "")
                relative_path = str(record.get("relative_path") or file_name)
                score, reason = self._score_file_match(
                    query=query,
                    terms=terms,
                    file_name=file_name,
                    relative_path=relative_path,
                    content="",
                    search_filename=request.search_filename,
                    search_content=False,
                )
                if score <= 0:
                    continue
                key = f"{source.id}:{relative_path}"
                matches_by_key[key] = IndexedFileSearchMatch(
                    event_id=str(record.get("content_event_id") or "") or None,
                    source_id=source.id,
                    file_name=file_name,
                    relative_path=relative_path,
                    extension=extension,
                    size_bytes=int(record.get("size_bytes") or 0),
                    modified_at=str(record.get("modified_at") or "") or None,
                    score=score,
                    match_reason=reason,
                    matched_excerpt="",
                    content_index_status=str(record.get("content_index_status") or "unknown"),
                    attachable=bool(record.get("is_attachable")),
                    readable=readable,
                    source_name=source.name,
                )

        for event in self._events.list_all_events(include_hidden=True):
            if event.source.value != "file_system" or event.type != "file_indexed":
                continue
            metadata = event.metadata or {}
            if metadata.get("missing") is True:
                continue
            source_id = str(metadata.get("source_id") or "")
            if request.source_ids and source_id not in request.source_ids:
                continue
            if request.connected_sources_only:
                if source_id not in source_cache:
                    source_cache[source_id] = self._sources.get_source(source_id) if source_id else None
                source = source_cache[source_id]
                if source is None or source.connector_type != "file_system" or not source.enabled:
                    continue
                if (source.config or {}).get("indexing_enabled") is not True:
                    continue
            extension = str(metadata.get("extension") or "").lower()
            if extensions and extension not in extensions:
                continue
            if request.attachable_only and extension in BLOCKED_ATTACHMENT_EXTENSIONS:
                continue
            readable = str(metadata.get("content_index_status") or "indexed") == "indexed"
            if request.readable_only and not readable:
                continue
            file_name = str(metadata.get("file_name") or event.title)
            relative_path = str(metadata.get("relative_path") or file_name)
            score, reason = self._score_file_match(
                query=query,
                terms=terms,
                file_name=file_name,
                relative_path=relative_path,
                content=event.content,
                search_filename=request.search_filename,
                search_content=request.search_content,
            )
            if score <= 0:
                continue
            key = f"{source_id}:{relative_path}"
            existing = matches_by_key.get(key)
            matched_excerpt = self._matched_excerpt(event.content, terms)
            if existing:
                combined_reasons = [existing.match_reason]
                if reason and reason not in existing.match_reason:
                    combined_reasons.append(reason)
                matches_by_key[key] = existing.model_copy(
                    update={
                        "event_id": event.id,
                        "score": min(1.0, max(existing.score, score) + (0.15 if score > 0 and existing.score > 0 else 0)),
                        "match_reason": ", ".join(combined_reasons),
                        "matched_excerpt": matched_excerpt,
                        "content_index_status": "indexed",
                        "attachable": existing.attachable or extension not in BLOCKED_ATTACHMENT_EXTENSIONS,
                        "readable": True,
                        "source_name": source_cache.get(source_id).name if source_cache.get(source_id) else existing.source_name,
                    }
                )
            else:
                source_name = None
                if source_id:
                    if source_id not in source_cache:
                        source_cache[source_id] = self._sources.get_source(source_id)
                    source_name = source_cache[source_id].name if source_cache.get(source_id) else None
                matches_by_key[key] = IndexedFileSearchMatch(
                    event_id=event.id,
                    source_id=source_id,
                    file_name=file_name,
                    relative_path=relative_path,
                    extension=extension,
                    size_bytes=int(metadata.get("size_bytes") or 0),
                    modified_at=str(metadata.get("modified_at") or "") or None,
                    score=score,
                    match_reason=reason,
                    matched_excerpt=matched_excerpt,
                    content_index_status="indexed",
                    attachable=extension not in BLOCKED_ATTACHMENT_EXTENSIONS,
                    readable=True,
                    source_name=source_name,
                )

        matches = list(matches_by_key.values())
        if request.latest_preference:
            matches.sort(key=lambda item: (item.modified_at or "", item.score), reverse=True)
        else:
            matches.sort(key=lambda item: (item.score, item.modified_at or ""), reverse=True)
        return IndexedFileSearchResponse(matches=matches[: request.limit])

    def resolve_attachments(self, request: ResolveIndexedAttachmentsRequest) -> ResolveIndexedAttachmentsResponse:
        for reference in request.files:
            if not self._safe_relative_segments(reference.relative_path):
                raise ValueError("Attachment path is invalid.")
        return ResolveIndexedAttachmentsResponse(attachments=[self.resolve_attachment(reference) for reference in request.files])

    def resolve_attachment(self, reference: IndexedFileAttachmentReference) -> ResolvedIndexedAttachment:
        try:
            path = self._resolve_connected_file_path(reference)
            extension = path.suffix.lower()
            size = path.stat().st_size if path.exists() else 0
            if extension in BLOCKED_ATTACHMENT_EXTENSIONS:
                return self._resolved_attachment(reference, path.name, extension, size, False, "Blocked file type.")
            if not path.exists() or not path.is_file():
                return self._resolved_attachment(reference, path.name, extension, size, False, "File is missing. Reindex the folder or choose another file.")
            if size > MAX_ATTACHMENT_BYTES:
                return self._resolved_attachment(reference, path.name, extension, size, False, "File exceeds the 20 MB attachment limit.")
            return self._resolved_attachment(reference, path.name, extension, size, True, None)
        except Exception as error:
            file_name = Path(reference.relative_path.replace("\\", "/")).name or "attachment"
            extension = file_name[file_name.rfind(".") :].lower() if "." in file_name else ""
            return self._resolved_attachment(reference, file_name, extension, 0, False, str(error))

    def resolve_connected_file_path(self, reference: IndexedFileAttachmentReference) -> Path:
        return self._resolve_connected_file_path(reference)

    def read_indexed_attachments(self, references: list[IndexedFileAttachmentReference]) -> list[dict[str, object]]:
        attachments: list[dict[str, object]] = []
        total_size = 0
        for reference in references:
            resolved = self.resolve_attachment(reference)
            if not resolved.attachable:
                raise ValueError(f"{resolved.file_name}: {resolved.reason or 'File cannot be attached.'}")
            path = self._resolve_connected_file_path(reference)
            content = path.read_bytes()
            size = len(content)
            total_size += size
            if total_size > MAX_ATTACHMENT_BYTES:
                raise ValueError("Attachment total size is too large. Keep attachments under 20 MB.")
            attachments.append(
                {
                    "filename": path.name,
                    "content_type": "application/octet-stream",
                    "content": content,
                    "size": size,
                    "source_id": reference.source_id,
                    "relative_path": reference.relative_path,
                }
            )
        return attachments

    def read_indexed_documents(
        self,
        references: list[IndexedFileAttachmentReference],
        *,
        max_chars_per_file: int = 30_000,
        max_total_chars: int = 120_000,
    ) -> tuple[list[DocumentSummaryInputFile], list[DocumentSummarySkippedFile], list[str], str]:
        files: list[DocumentSummaryInputFile] = []
        skipped: list[DocumentSummarySkippedFile] = []
        warnings: list[str] = []
        total_chars = 0
        folder_name = "connected folders"

        for reference in references[:20]:
            try:
                source = self._sources.get_source(reference.source_id)
                if source and folder_name == "connected folders":
                    folder_name = source.name or Path(source.path).name or folder_name
                path = self._resolve_connected_file_path(reference)
                extension = path.suffix.lower()
                if extension not in READABLE_CONTENT_EXTENSIONS:
                    skipped.append(DocumentSummarySkippedFile(relative_path=reference.relative_path, reason="File type is not readable for summaries."))
                    continue
                if path.stat().st_size > 5 * 1024 * 1024:
                    skipped.append(DocumentSummarySkippedFile(relative_path=reference.relative_path, reason="File exceeds the 5 MB summary limit."))
                    continue
                remaining = max_total_chars - total_chars
                if remaining <= 0:
                    skipped.append(DocumentSummarySkippedFile(relative_path=reference.relative_path, reason="Summary text limit reached."))
                    continue
                text = self._extract_text(path, min(max_chars_per_file, remaining)).strip()
                if not text:
                    skipped.append(DocumentSummarySkippedFile(relative_path=reference.relative_path, reason="No readable text extracted."))
                    continue
                total_chars += len(text)
                files.append(DocumentSummaryInputFile(relative_path=reference.relative_path, extension=extension, text=text))
            except Exception as error:
                skipped.append(DocumentSummarySkippedFile(relative_path=reference.relative_path, reason=str(error)))

        if len(references) > 20:
            warnings.append("Only the first 20 selected files were read for this summary.")
        if total_chars >= max_total_chars:
            warnings.append(f"Summary used the first {max_total_chars:,} extracted characters due to size limits.")
        return files, skipped, warnings, folder_name

    def _source_allowed_for_search(self, source: ConnectorSource, request: IndexedFileSearchRequest) -> bool:
        if request.source_ids and source.id not in request.source_ids:
            return False
        if request.connected_sources_only:
            if source.connector_type != "file_system" or not source.enabled:
                return False
            if (source.config or {}).get("indexing_enabled") is not True:
                return False
        return True

    def _inventory_records(self, source: ConnectorSource) -> list[dict[str, Any]]:
        raw = (source.config or {}).get("file_inventory")
        if isinstance(raw, list):
            return [record for record in raw if isinstance(record, dict)]
        return []

    def _inventory_record(
        self,
        *,
        source: ConnectorSource,
        root_hash: str,
        path: Path,
        relative_path: str,
        content_index_status: str,
        content_index_error: str | None = None,
        content_event_id: str | None = None,
    ) -> dict[str, Any]:
        stat = path.stat()
        extension = path.suffix.lower()
        modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        is_attachable = extension not in BLOCKED_ATTACHMENT_EXTENSIONS and int(stat.st_size) <= MAX_ATTACHMENT_BYTES
        return {
            "id": hashlib.sha256(f"{source.id}:{relative_path}".encode("utf-8")).hexdigest(),
            "source_id": source.id,
            "root_path_hash": root_hash,
            "relative_path": relative_path,
            "file_name": path.name,
            "extension": extension,
            "size_bytes": int(stat.st_size),
            "modified_at": modified_at,
            "content_hash": None,
            "is_safe_file": True,
            "is_attachable": is_attachable,
            "is_readable_candidate": extension in READABLE_CONTENT_EXTENSIONS,
            "content_index_status": content_index_status,
            "content_index_error": content_index_error,
            "content_event_id": content_event_id,
            "indexed_text_chars": 0,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "missing": False,
            "missing_at": None,
        }

    def _merge_inventory_records(
        self,
        source: ConnectorSource,
        current_records: dict[str, dict[str, Any]],
        seen_keys: set[str],
    ) -> tuple[list[dict[str, Any]], int]:
        now = datetime.now(timezone.utc).isoformat()
        merged: dict[str, dict[str, Any]] = {}
        for record in self._inventory_records(source):
            relative_path = str(record.get("relative_path") or "")
            if not relative_path:
                continue
            key = f"{source.id}:{relative_path}"
            if key in seen_keys:
                continue
            missing_record = dict(record)
            if missing_record.get("missing") is not True:
                missing_record["missing"] = True
                missing_record["missing_at"] = now
            merged[key] = missing_record
        merged.update(current_records)
        records = sorted(merged.values(), key=lambda item: str(item.get("relative_path") or "").lower())
        missing_count = sum(1 for record in records if record.get("missing") is True)
        return records[:5000], missing_count

    def _iter_files(self, root: Path, config: dict[str, Any], state: dict[str, Any]):
        max_files = int(config["max_files"])
        max_depth = int(config["max_depth"])
        recursive = bool(config["recursive"])

        def walk(path: Path, depth: int):
            if state["file_count"] >= max_files:
                self._warn(state, f"Indexing was limited to {max_files} files.")
                return
            if depth > max_depth:
                self._warn(state, f"Depth limit reached at {max_depth}; deeper folders skipped.")
                return
            try:
                entries = sorted(path.iterdir(), key=lambda item: item.name.lower())
            except (OSError, PermissionError) as error:
                self._warn(state, f"Could not access {path.name}: {error}")
                return

            for entry in entries:
                if state["file_count"] >= max_files:
                    self._warn(state, f"Indexing was limited to {max_files} files.")
                    return
                try:
                    if entry.is_symlink():
                        self._skip(state, root, entry, "Symlink skipped.")
                        continue
                    if self._excluded(root, entry, config):
                        continue
                    if entry.is_dir():
                        if recursive:
                            yield from walk(entry, depth + 1)
                        continue
                    if not entry.is_file():
                        continue
                    state["file_count"] += 1
                    skip_reason = self._file_skip_reason(root, entry, config, state)
                    if skip_reason:
                        self._skip(state, root, entry, skip_reason)
                        continue
                    yield entry
                except (OSError, PermissionError) as error:
                    self._skip(state, root, entry, f"Could not inspect file: {error}")

        yield from walk(root, 0)

    def _resolve_connected_file_path(self, reference: IndexedFileAttachmentReference) -> Path:
        source = self._sources.get_source(reference.source_id)
        if source is None:
            raise ValueError("Connected folder source was not found.")
        if source.connector_type != "file_system" or not source.enabled:
            raise ValueError("Connected folder source is not enabled.")
        if (source.config or {}).get("indexing_enabled") is not True:
            raise ValueError("This file is not from an indexed connected folder.")
        segments = self._safe_relative_segments(reference.relative_path)
        if not segments:
            raise ValueError("Attachment path is invalid.")
        root = validate_root_path(source.path)
        path = root.joinpath(*segments).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError("Attachment path is outside the connected folder.") from error
        return path

    def _safe_relative_segments(self, relative_path: str) -> list[str]:
        normalized = relative_path.replace("\\", "/").strip()
        if not normalized or normalized.startswith("/") or ":" in normalized:
            return []
        segments = [segment for segment in normalized.split("/") if segment]
        if any(segment in {".", ".."} for segment in segments):
            return []
        return segments

    def _resolved_attachment(
        self,
        reference: IndexedFileAttachmentReference,
        file_name: str,
        extension: str,
        size_bytes: int,
        attachable: bool,
        reason: str | None,
    ) -> ResolvedIndexedAttachment:
        return ResolvedIndexedAttachment(
            id=f"{reference.source_id}:{reference.relative_path}",
            file_name=file_name,
            source_id=reference.source_id,
            relative_path=reference.relative_path,
            size_bytes=size_bytes,
            extension=extension,
            attachable=attachable,
            reason=reason,
        )

    def _index_file(self, source: ConnectorSource, root: Path, root_hash: str, path: Path, relative_path: str, config: dict[str, Any]) -> dict[str, Any]:
        stat = path.stat()
        if path.suffix.lower() not in READABLE_CONTENT_EXTENSIONS:
            return {
                "event_id": None,
                "dedupe_key": f"{source.id}:{relative_path}",
                "created": False,
                "updated": False,
                "unchanged": False,
                "indexed_text_chars": 0,
                "content_index_status": "not_readable",
                "content_index_error": "This file type is attachable but not readable for content indexing.",
            }
        extracted = self._extract_text(path, int(config["max_extracted_chars_per_file"]))
        content_hash = hashlib.sha256(extracted.encode("utf-8")).hexdigest()
        dedupe_key = f"{source.id}:{relative_path}"
        modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        existing = self._events.find_event_by_metadata("file_system", "file_indexed", "dedupe_key", dedupe_key)
        if (
            existing
            and existing.metadata.get("content_hash") == content_hash
            and existing.metadata.get("modified_at") == modified_at
            and existing.metadata.get("missing") is not True
        ):
            return {
                "event_id": existing.id,
                "dedupe_key": dedupe_key,
                "created": False,
                "updated": False,
                "unchanged": True,
                "indexed_text_chars": len(extracted),
                "content_index_status": "indexed",
                "content_index_error": None,
            }

        metadata = {
            "dedupe_key": dedupe_key,
            "source_id": source.id,
            "root_path_hash": root_hash,
            "relative_path": relative_path,
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": int(stat.st_size),
            "modified_at": modified_at,
            "content_hash": content_hash,
            "indexed_text_chars": len(extracted),
            "file_category": self._file_category(path.suffix.lower()),
            "is_readable_file": True,
            "missing": False,
            "missing_at": None,
        }
        content = "\n".join(
            [
                f"Path: {relative_path}",
                f"Type: {path.suffix.lower()}",
                f"Modified: {modified_at}",
                "",
                "Excerpt:",
                extracted,
            ]
        ).strip()
        title = f"File: {path.name}"
        timestamp = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        if existing:
            updated = self._events.update_event_content_and_metadata(existing.id, content, metadata, title=title, timestamp=timestamp)
            if updated:
                self._reindex_updated_event(updated)
            return {
                "event_id": existing.id,
                "dedupe_key": dedupe_key,
                "created": False,
                "updated": True,
                "unchanged": False,
                "indexed_text_chars": len(extracted),
                "content_index_status": "indexed",
                "content_index_error": None,
            }
        event = self._events.create_event(
            {
                "source": EventSource.file_system,
                "type": "file_indexed",
                "title": title,
                "content": content,
                "metadata": metadata,
                "timestamp": timestamp,
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        return {
            "event_id": event.id,
            "dedupe_key": dedupe_key,
            "created": True,
            "updated": False,
            "unchanged": False,
            "indexed_text_chars": len(extracted),
            "content_index_status": "indexed",
            "content_index_error": None,
        }

    def _mark_missing_files(self, source_id: str, seen_dedupe_keys: set[str]) -> int:
        missing_count = 0
        now = datetime.now(timezone.utc).isoformat()
        for event in self._events.list_all_events(include_hidden=True):
            if event.source.value != "file_system" or event.type != "file_indexed":
                continue
            metadata = dict(event.metadata or {})
            if metadata.get("source_id") != source_id:
                continue
            dedupe_key = str(metadata.get("dedupe_key") or "")
            if not dedupe_key or dedupe_key in seen_dedupe_keys or metadata.get("missing") is True:
                continue
            metadata["missing"] = True
            metadata["missing_at"] = now
            relative_path = str(metadata.get("relative_path") or event.title)
            content = "\n".join(
                [
                    f"Path: {relative_path}",
                    "Status: missing",
                    f"Missing since: {now}",
                    "",
                    "This file was previously indexed from a connected folder but was not found during the latest background index pass.",
                ]
            )
            updated = self._events.update_event_content_and_metadata(event.id, content, metadata, title=event.title, timestamp=event.timestamp)
            if updated:
                self._reindex_updated_event(updated)
            missing_count += 1
        return missing_count

    def _extract_text(self, path: Path, max_chars: int) -> str:
        extension = path.suffix.lower()
        if extension == ".pdf":
            return self._extract_pdf_text(path, max_chars)
        if extension == ".docx":
            return self._extract_docx_text(path, max_chars)
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]

    def _extract_pdf_text(self, path: Path, max_chars: int) -> str:
        try:
            from pypdf import PdfReader
        except Exception as error:
            raise ValueError("PDF extraction dependency is not installed.") from error
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(f"--- Page {index} ---\n{text.strip()}")
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                break
        combined = "\n\n".join(chunks).strip()
        if not combined:
            raise ValueError("No selectable text found. This PDF may be scanned/image-based.")
        return combined[:max_chars]

    def _extract_docx_text(self, path: Path, max_chars: int) -> str:
        try:
            from docx import Document
        except Exception as error:
            raise ValueError("DOCX extraction dependency is not installed.") from error
        document = Document(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()).strip()
        if not text:
            raise ValueError("Could not extract text from DOCX.")
        return text[:max_chars]

    def _file_skip_reason(self, root: Path, path: Path, config: dict[str, Any], state: dict[str, Any]) -> str | None:
        extension = path.suffix.lower()
        if path.name.lower() in BLOCKED_NAMES or extension in BLOCKED_FILE_INDEX_EXTENSIONS:
            return "Blocked file type."
        if is_hidden(path) and not bool(config["include_hidden"]):
            return "Hidden file skipped."
        if extension not in set(config["include_patterns"]):
            return "File type is not configured for indexing."
        if path.stat().st_size > int(config["max_file_size_mb"]) * 1024 * 1024:
            return f"File exceeds {config['max_file_size_mb']} MB limit."
        return None

    def _excluded(self, root: Path, path: Path, config: dict[str, Any]) -> bool:
        relative = str(path.resolve().relative_to(root)).replace("\\", "/")
        parts = set(relative.split("/"))
        for pattern in config["exclude_patterns"]:
            if pattern in parts or fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        return False

    def _skip(self, state: dict[str, Any], root: Path, path: Path, reason: str) -> None:
        try:
            relative = str(path.resolve().relative_to(root))
        except Exception:
            relative = path.name
        state["skipped"].append({"relative_path": relative, "reason": reason})

    def _warn(self, state: dict[str, Any], message: str) -> None:
        if message not in state["warnings"]:
            state["warnings"].append(message)

    def _normalized_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": bool(config.get("enabled", True)),
            "indexing_enabled": bool(config.get("indexing_enabled", True)),
            "recursive": bool(config.get("recursive", True)),
            "max_depth": max(0, min(int(config.get("max_depth", 5)), 10)),
            "max_files": max(1, min(int(config.get("max_files", 2000)), 5000)),
            "include_patterns": self._normalize_extensions(config.get("include_patterns") or config.get("allowed_extensions") or DEFAULT_FILE_INDEX_EXTENSIONS),
            "exclude_patterns": config.get("exclude_patterns") or DEFAULT_EXCLUDE_PATTERNS,
            "max_file_size_mb": max(1, min(int(config.get("max_file_size_mb", 5)), 25)),
            "max_extracted_chars_per_file": max(1000, min(int(config.get("max_extracted_chars_per_file", MAX_EXTRACTED_CHARS_PER_FILE)), 100_000)),
            "include_hidden": bool(config.get("include_hidden", False)),
        }

    def _normalize_extensions(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return list(DEFAULT_FILE_INDEX_EXTENSIONS)
        extensions = []
        for value in values:
            text = str(value).strip().lower()
            if not text:
                continue
            if text.startswith("*."):
                text = text[1:]
            if not text.startswith("."):
                text = f".{text}"
            if text not in BLOCKED_FILE_INDEX_EXTENSIONS:
                extensions.append(text)
        return extensions or list(DEFAULT_FILE_INDEX_EXTENSIONS)

    def _update_source_index_metadata(self, source: ConnectorSource, result: FileIndexRunResult, inventory_records: list[dict[str, Any]]) -> None:
        config = dict(source.config or {})
        failed_inventory = [
            {
                "relative_path": str(record.get("relative_path") or ""),
                "file_name": str(record.get("file_name") or ""),
                "reason": str(record.get("content_index_error") or "Content extraction failed."),
                "content_index_status": str(record.get("content_index_status") or "failed"),
                "is_attachable": bool(record.get("is_attachable")),
            }
            for record in inventory_records
            if record.get("content_index_status") == "failed" and record.get("missing") is not True
        ][:100]
        config.update(
            {
                "last_indexed_at": result.completed_at.isoformat(),
                "file_count": result.file_count,
                "inventory_count": result.inventory_count,
                "indexed_count": result.indexed_count,
                "content_indexed_count": result.indexed_count,
                "content_failed_count": result.content_failed_count,
                "skipped_count": result.skipped_count,
                "missing_count": result.missing_count,
                "file_inventory": inventory_records,
                "content_failed_files": failed_inventory,
                "last_error": None if result.failed_count == 0 else f"{result.failed_count} file(s) failed.",
            }
        )
        self._sources.update_source(source.id, {"config": config})

    def _reindex_updated_event(self, event) -> None:
        try:
            from app.integrations.vector_store.chroma_vector_store import chroma_vector_store

            chroma_vector_store.delete_event(event.id)
        except Exception:
            pass
        try:
            from app.services.embedding_index_service import embedding_index_service

            embedding_index_service.index_event(event)
        except Exception:
            self._events.update_embedding_status(event.id, EmbeddingStatus.pending.value)

    def _score_file_match(
        self,
        *,
        query: str,
        terms: list[str],
        file_name: str,
        relative_path: str,
        content: str,
        search_filename: bool,
        search_content: bool,
    ) -> tuple[float, str]:
        haystack_name = f"{file_name} {relative_path}".lower()
        haystack_content = content.lower()
        score = 0.0
        reasons: list[str] = []
        if search_filename:
            if query in haystack_name:
                score += 0.7
                reasons.append("filename matched query")
            else:
                matching_terms = [term for term in terms if term in haystack_name]
                resume_terms = [term for term in matching_terms if term in {"resume", "cv", "curriculum", "vitae"}]
                if resume_terms:
                    score += 0.75
                    reasons.append(f"filename matched {resume_terms[0]}")
                elif matching_terms:
                    term_hits = len(matching_terms)
                    score += min(0.55, 0.2 * term_hits)
                    reasons.append("filename keyword match")
        if search_content:
            if query in haystack_content:
                score += 0.55
                reasons.append("content matched query")
            else:
                term_hits = sum(1 for term in terms if term in haystack_content)
                if term_hits:
                    score += min(0.45, 0.15 * term_hits)
                    reasons.append("content keyword match")
        return min(score, 1.0), ", ".join(reasons) or "matched"

    def _matched_excerpt(self, content: str, terms: list[str]) -> str:
        lowered = content.lower()
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        if not positions:
            return content[:240]
        start = max(0, min(positions) - 80)
        return content[start : start + 300].strip()

    def _file_category(self, extension: str) -> str:
        if extension in {".log"}:
            return "log"
        if extension in {".json", ".csv", ".xml", ".yaml", ".yml"}:
            return "data"
        if extension in {".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".sql"}:
            return "code"
        return "document"


file_index_service = FileIndexService()
