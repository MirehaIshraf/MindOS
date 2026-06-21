from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.repositories.base import EventRepository
from app.services.file_snapshot_service import is_hidden, validate_root_path
from app.services.mcp_config_service import mcp_config_service
from app.services.mcp_file_reader_service import READABLE_MCP_EXTENSIONS, mcp_file_reader_service


MAX_MCP_FILE_BYTES = 25 * 1024 * 1024
MAX_MCP_EXTRACTED_CHARS = 60_000
MAX_MCP_TOTAL_CHARS = 1_500_000
DEFAULT_EXCLUDE_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__"}


class McpFileIndexService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._events = event_repository or get_event_repository()

    def index_configured_root(self, reason: str = "manual") -> dict[str, Any]:
        config = mcp_config_service.get_filesystem_config()
        root_path = str(config.get("root_path") or "")
        if not root_path:
            raise ValueError("File System MCP root path is not configured.")
        return self.index_folder(
            root_path=root_path,
            max_depth=int(config.get("max_depth") or 5),
            max_files=int(config.get("max_files") or 2000),
            recursive=bool(config.get("recursive", True)),
            reason=reason,
        )

    def index_folder(
        self,
        *,
        root_path: str,
        max_depth: int = 5,
        max_files: int = 2000,
        recursive: bool = True,
        reason: str = "manual",
    ) -> dict[str, Any]:
        root = validate_root_path(root_path)
        max_depth = max(0, min(int(max_depth), 10))
        max_files = max(1, min(int(max_files), 5000))
        root_hash = self._root_hash(root)
        started_at = datetime.now(timezone.utc)
        mcp_config_service.update_filesystem_status({"index_status": "indexing", "last_error": None})

        state: dict[str, Any] = {
            "inventory_count": 0,
            "indexed_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "missing_count": 0,
            "total_chars": 0,
            "warnings": [],
            "failed": [],
            "skipped": [],
            "event_ids": [],
            "seen_keys": set(),
        }

        try:
            for path in self._iter_files(root, max_depth=max_depth, max_files=max_files, recursive=recursive, state=state):
                relative_path = str(path.resolve().relative_to(root))
                state["inventory_count"] += 1
                dedupe_key = self._dedupe_key(root_hash, relative_path)
                state["seen_keys"].add(dedupe_key)
                if state["total_chars"] >= MAX_MCP_TOTAL_CHARS:
                    self._skip(state, relative_path, "Indexing run text limit reached.")
                    continue
                try:
                    result = self._index_file(root, root_hash, path, relative_path, dedupe_key)
                    state["total_chars"] += int(result.get("indexed_text_chars") or 0)
                    if result.get("event_id"):
                        state["event_ids"].append(result["event_id"])
                    if result.get("indexed"):
                        state["indexed_count"] += 1
                    if result.get("updated"):
                        state["updated_count"] += 1
                    if result.get("unchanged"):
                        state["unchanged_count"] += 1
                except Exception as error:
                    state["failed_count"] += 1
                    state["failed"].append({"relative_path": relative_path, "reason": str(error)})

            state["missing_count"] = self._mark_missing(root_hash, state["seen_keys"])
            completed_at = datetime.now(timezone.utc)
            payload = {
                "root_path": str(root),
                "root_path_hash": root_hash,
                "reason": reason,
                "inventory_count": state["inventory_count"],
                "indexed_count": state["indexed_count"],
                "updated_count": state["updated_count"],
                "unchanged_count": state["unchanged_count"],
                "failed_count": state["failed_count"],
                "skipped_count": state["skipped_count"],
                "missing_count": state["missing_count"],
                "warnings": state["warnings"][:20],
                "failed": state["failed"][:50],
                "skipped": state["skipped"][:50],
                "event_ids": state["event_ids"],
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "message": (
                    f"Indexed {state['indexed_count']} readable file(s), "
                    f"updated {state['updated_count']}, failed {state['failed_count']}, "
                    f"marked {state['missing_count']} missing."
                ),
            }
            mcp_config_service.update_filesystem_status(
                {
                    "index_status": "idle",
                    "inventory_count": state["inventory_count"],
                    "indexed_count": state["indexed_count"],
                    "missing_count": state["missing_count"],
                    "last_indexed_at": completed_at.isoformat(),
                    "last_error": None if state["failed_count"] == 0 else f"{state['failed_count']} file(s) failed.",
                    "last_index_result": payload,
                }
            )
            return payload
        except Exception as error:
            mcp_config_service.update_filesystem_status({"index_status": "error", "last_error": str(error)})
            raise

    def search_files(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        normalized_query = query.strip().lower()
        terms = [term for term in normalized_query.replace("-", " ").replace("_", " ").split() if len(term) > 1]
        matches: list[dict[str, Any]] = []
        for event in self._mcp_events():
            metadata = event.metadata or {}
            if metadata.get("missing") is True:
                continue
            file_name = str(metadata.get("file_name") or event.title)
            relative_path = str(metadata.get("relative_path") or file_name)
            score, reason = self._score_match(normalized_query, terms, file_name, relative_path, event.content)
            if score <= 0:
                continue
            matches.append(
                {
                    "event_id": event.id,
                    "file_name": file_name,
                    "relative_path": relative_path,
                    "extension": metadata.get("extension"),
                    "score": score,
                    "match_reason": reason,
                    "content_preview": event.content[:500],
                    "indexed_text_chars": metadata.get("indexed_text_chars", 0),
                    "visual_extraction_status": metadata.get("visual_extraction_status", "not_required"),
                }
            )
        matches.sort(key=lambda item: item["score"], reverse=True)
        return matches[: max(1, min(limit, 50))]

    def read_indexed_file(self, relative_path: str | None = None, event_id: str | None = None) -> dict[str, Any]:
        event = self._event_for_reference(relative_path=relative_path, event_id=event_id)
        metadata = event.metadata or {}
        return {
            "event_id": event.id,
            "file_name": metadata.get("file_name") or event.title,
            "relative_path": metadata.get("relative_path"),
            "extension": metadata.get("extension"),
            "content": event.content,
            "indexed_text_chars": metadata.get("indexed_text_chars", len(event.content)),
            "visual_extraction_status": metadata.get("visual_extraction_status", "not_required"),
            "warnings": metadata.get("reader_warnings", []),
            "missing": metadata.get("missing") is True,
        }

    def _event_for_reference(self, relative_path: str | None, event_id: str | None):
        if event_id:
            event = self._events.get_event_by_id(event_id)
            if event and self._is_mcp_file_event(event):
                return event
            raise ValueError("Indexed MCP file was not found.")
        wanted = (relative_path or "").replace("\\", "/").strip().lower()
        if not wanted:
            raise ValueError("A file reference is required.")
        for event in self._mcp_events():
            metadata = event.metadata or {}
            event_path = str(metadata.get("relative_path") or "").replace("\\", "/").lower()
            if event_path == wanted or event_path.endswith("/" + wanted) or str(metadata.get("file_name") or "").lower() == wanted:
                return event
        raise ValueError("Indexed MCP file was not found.")

    def _index_file(self, root: Path, root_hash: str, path: Path, relative_path: str, dedupe_key: str) -> dict[str, Any]:
        read_result = mcp_file_reader_service.read_text(path, MAX_MCP_EXTRACTED_CHARS)
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        content_hash = hashlib.sha256(read_result.text.encode("utf-8")).hexdigest()
        existing = self._events.find_event_by_metadata("file_system", "file_indexed", "dedupe_key", dedupe_key)

        if (
            existing
            and existing.metadata.get("content_hash") == content_hash
            and existing.metadata.get("modified_at") == modified_at
            and existing.metadata.get("missing") is not True
        ):
            return {"event_id": existing.id, "indexed": True, "updated": False, "unchanged": True, "indexed_text_chars": len(read_result.text)}

        metadata = {
            "mcp_server_id": "filesystem",
            "dedupe_key": dedupe_key,
            "root_path_hash": root_hash,
            "relative_path": relative_path,
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": int(stat.st_size),
            "modified_at": modified_at,
            "content_hash": content_hash,
            "indexed_text_chars": len(read_result.text),
            "reader_content_type": read_result.content_type,
            "reader_warnings": list(read_result.warnings),
            "visual_extraction_status": read_result.visual_extraction_status,
            "missing": False,
            "missing_at": None,
        }
        content = "\n".join(
            [
                f"Path: {relative_path}",
                f"Type: {path.suffix.lower()}",
                f"Modified: {modified_at}",
                "",
                "Extracted content:",
                read_result.text or "[No selectable text extracted.]",
            ]
        ).strip()
        title = f"File: {path.name}"
        timestamp = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        if existing:
            updated = self._events.update_event_content_and_metadata(existing.id, content, metadata, title=title, timestamp=timestamp)
            if updated:
                self._reindex_updated_event(updated)
            return {"event_id": existing.id, "indexed": True, "updated": True, "unchanged": False, "indexed_text_chars": len(read_result.text)}

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
        return {"event_id": event.id, "indexed": True, "updated": False, "unchanged": False, "indexed_text_chars": len(read_result.text)}

    def _iter_files(self, root: Path, *, max_depth: int, max_files: int, recursive: bool, state: dict[str, Any]):
        def walk(path: Path, depth: int):
            if state["inventory_count"] + state["skipped_count"] >= max_files:
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
                try:
                    if entry.is_symlink():
                        self._skip(state, str(entry.resolve().relative_to(root)), "Symlink skipped.")
                        continue
                    if entry.is_dir():
                        if entry.name in DEFAULT_EXCLUDE_DIRS:
                            continue
                        if recursive:
                            yield from walk(entry, depth + 1)
                        continue
                    if not entry.is_file():
                        continue
                    relative_path = str(entry.resolve().relative_to(root))
                    skip_reason = self._skip_reason(entry)
                    if skip_reason:
                        self._skip(state, relative_path, skip_reason)
                        continue
                    yield entry
                except (OSError, PermissionError) as error:
                    self._skip(state, entry.name, f"Could not inspect file: {error}")

        yield from walk(root, 0)

    def _skip_reason(self, path: Path) -> str | None:
        if mcp_file_reader_service.is_blocked(path):
            return "Blocked file type."
        if is_hidden(path):
            return "Hidden/system file skipped."
        if path.suffix.lower() not in READABLE_MCP_EXTENSIONS:
            return "Unsupported readable file type."
        if path.stat().st_size > MAX_MCP_FILE_BYTES:
            return "File exceeds 25 MB limit."
        return None

    def _mark_missing(self, root_hash: str, seen_keys: set[str]) -> int:
        missing_count = 0
        now = datetime.now(timezone.utc).isoformat()
        for event in self._mcp_events():
            metadata = dict(event.metadata or {})
            if metadata.get("root_path_hash") != root_hash:
                continue
            dedupe_key = str(metadata.get("dedupe_key") or "")
            if not dedupe_key or dedupe_key in seen_keys or metadata.get("missing") is True:
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
                    "This file was previously indexed by File System MCP but was not found during the latest index pass.",
                ]
            )
            updated = self._events.update_event_content_and_metadata(event.id, content, metadata, title=event.title, timestamp=event.timestamp)
            if updated:
                self._reindex_updated_event(updated)
            missing_count += 1
        return missing_count

    def _mcp_events(self):
        return [event for event in self._events.list_all_events(include_hidden=True) if self._is_mcp_file_event(event)]

    def _is_mcp_file_event(self, event) -> bool:
        return event.source.value == "file_system" and event.type == "file_indexed" and (event.metadata or {}).get("mcp_server_id") == "filesystem"

    def _score_match(self, query: str, terms: list[str], file_name: str, relative_path: str, content: str) -> tuple[float, str]:
        haystack_name = f"{file_name} {relative_path}".lower()
        haystack_content = content.lower()
        score = 0.0
        reasons: list[str] = []
        if query and query in haystack_name:
            score += 0.8
            reasons.append("filename matched query")
        if query and query in haystack_content:
            score += 0.55
            reasons.append("content matched query")
        for term in terms:
            if term in haystack_name:
                score += 0.25
            if term in haystack_content:
                score += 0.1
        if not reasons and score > 0:
            reasons.append("keyword match")
        return min(score, 1.0), ", ".join(reasons)

    def _root_hash(self, root: Path) -> str:
        return hashlib.sha256(str(root).encode("utf-8")).hexdigest()

    def _dedupe_key(self, root_hash: str, relative_path: str) -> str:
        return f"mcp:filesystem:{root_hash}:{relative_path}"

    def _skip(self, state: dict[str, Any], relative_path: str, reason: str) -> None:
        state["skipped_count"] += 1
        state["skipped"].append({"relative_path": relative_path, "reason": reason})

    def _warn(self, state: dict[str, Any], message: str) -> None:
        if message not in state["warnings"]:
            state["warnings"].append(message)

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


mcp_file_index_service = McpFileIndexService()
