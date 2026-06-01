from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.core.dependencies import get_event_repository, get_relationship_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.domain.models import Event
from app.repositories.base import EventRepository, RelationshipRepository
from app.services.browser_importance_service import browser_importance_service
from app.services.browser_content_quality_service import content_quality_from_capture
from app.services.embedding_index_service import embedding_index_service
from app.services.relationship_service import relationship_service
from app.services.url_normalization_service import classify_url_page_type, normalize_url, url_hash


class BrowserMemoryService:
    def __init__(
        self,
        event_repository: EventRepository | None = None,
        relationship_repository: RelationshipRepository | None = None,
    ) -> None:
        self._event_repository = event_repository or get_event_repository()
        self._relationship_repository = relationship_repository or get_relationship_repository()

    def ingest_browser_event(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        metadata: dict[str, Any],
        timestamp: datetime,
        config: dict[str, Any],
    ) -> Event:
        if str(config.get("capture_mode") or "manual") == "off":
            raise PermissionError("Browser capture mode is off.")
        if event_type == "browser_page_captured":
            return self.upsert_browser_page_capture(title, content, metadata, timestamp, config)
        if event_type == "browser_page_seen":
            return self.upsert_browser_page_seen(title, content, metadata, timestamp)
        if event_type == "browser_search_query":
            return self.upsert_browser_search_query(title, content, metadata, timestamp, config)
        return self._event_repository.create_event(
            {
                "source": EventSource.browser_extension,
                "type": event_type,
                "title": title,
                "content": content,
                "metadata": metadata,
                "timestamp": timestamp,
                "embedding_status": EmbeddingStatus.not_required,
            }
        )

    def upsert_browser_page_capture(
        self,
        title: str,
        content: str,
        metadata: dict[str, Any],
        timestamp: datetime,
        config: dict[str, Any],
    ) -> Event:
        metadata = self._browser_metadata(metadata, content, config)
        normalized_hash = str(metadata["normalized_url_hash"])
        existing = self._event_repository.find_event_by_metadata("browser_extension", "browser_page_captured", "normalized_url_hash", normalized_hash)
        prepared_content, metadata = self._prepare_capture_content(title, content, metadata)
        if existing is None:
            metadata["visit_count"] = int(metadata.get("visit_count") or 1)
            metadata["first_seen_at"] = metadata.get("first_seen_at") or timestamp.isoformat()
            metadata["last_seen_at"] = timestamp.isoformat()
            metadata["last_captured_at"] = timestamp.isoformat()
            event = self._event_repository.create_event(
                {
                    "source": EventSource.browser_extension,
                    "type": "browser_page_captured",
                    "title": title,
                    "content": prepared_content,
                    "metadata": metadata,
                    "timestamp": timestamp,
                    "embedding_status": EmbeddingStatus.not_required,
                }
            )
            self._safe_relationships(event)
            return event

        merged_metadata = dict(existing.metadata)
        merged_metadata.update(metadata)
        merged_metadata["visit_count"] = int(existing.metadata.get("visit_count") or 1) + 1
        merged_metadata["first_seen_at"] = existing.metadata.get("first_seen_at") or existing.timestamp.isoformat()
        merged_metadata["last_seen_at"] = timestamp.isoformat()
        merged_metadata["last_captured_at"] = timestamp.isoformat()
        should_replace = self._is_better_content(prepared_content, existing.content, merged_metadata, existing.metadata)
        updated_content = prepared_content if should_replace else existing.content
        updated = self._event_repository.update_event_content_and_metadata(
            existing.id,
            updated_content,
            merged_metadata,
            title=title or existing.title,
            timestamp=timestamp,
        ) or existing
        if should_replace:
            embedding_index_service.index_event(updated)
        return updated

    def upsert_browser_page_seen(self, title: str, content: str, metadata: dict[str, Any], timestamp: datetime) -> Event:
        metadata = self._url_identity(metadata)
        metadata["seen_day"] = timestamp.date().isoformat()
        key = f"{metadata['normalized_url_hash']}:{metadata['seen_day']}"
        metadata["history_key"] = key
        existing = self._event_repository.find_event_by_metadata("browser_extension", "browser_page_seen", "history_key", key)
        if existing is None:
            metadata.update({"visit_count": 1, "first_seen_at": timestamp.isoformat(), "last_seen_at": timestamp.isoformat()})
            return self._event_repository.create_event(
                {
                    "source": EventSource.browser_extension,
                    "type": "browser_page_seen",
                    "title": title,
                    "content": content,
                    "metadata": metadata,
                    "timestamp": timestamp,
                    "embedding_status": EmbeddingStatus.not_required,
                }
            )
        merged = dict(existing.metadata)
        merged.update(metadata)
        merged["visit_count"] = int(existing.metadata.get("visit_count") or 1) + 1
        merged["first_seen_at"] = existing.metadata.get("first_seen_at") or existing.timestamp.isoformat()
        merged["last_seen_at"] = timestamp.isoformat()
        return self._event_repository.update_event_content_and_metadata(existing.id, existing.content, merged, title=existing.title, timestamp=timestamp) or existing

    def upsert_browser_search_query(
        self,
        title: str,
        content: str,
        metadata: dict[str, Any],
        timestamp: datetime,
        config: dict[str, Any],
    ) -> Event:
        if not bool(config.get("capture_search_queries", True)):
            raise PermissionError("Browser search query capture is disabled.")
        query, search_engine = browser_importance_service.extract_search_query(str(metadata.get("url") or ""))
        metadata["query"] = str(metadata.get("query") or query or "").strip()
        metadata["search_engine"] = str(metadata.get("search_engine") or search_engine or "search")
        if not metadata["query"]:
            raise ValueError("browser_search_query requires a query.")
        metadata["search_day"] = timestamp.date().isoformat()
        metadata["search_key"] = f"{metadata['search_engine']}:{metadata['query'].lower()}:{metadata['search_day']}"
        existing = self._event_repository.find_event_by_metadata("browser_extension", "browser_search_query", "search_key", metadata["search_key"])
        title = f"Searched: {metadata['query']}"
        content = f"Search query: {metadata['query']}"
        if existing is None:
            metadata.update({"search_count": 1, "first_seen_at": timestamp.isoformat(), "last_seen_at": timestamp.isoformat()})
            return self._event_repository.create_event(
                {
                    "source": EventSource.browser_extension,
                    "type": "browser_search_query",
                    "title": title,
                    "content": content,
                    "metadata": metadata,
                    "timestamp": timestamp,
                    "embedding_status": EmbeddingStatus.not_required,
                }
            )
        merged = dict(existing.metadata)
        merged.update(metadata)
        merged["search_count"] = int(existing.metadata.get("search_count") or 1) + 1
        merged["first_seen_at"] = existing.metadata.get("first_seen_at") or existing.timestamp.isoformat()
        merged["last_seen_at"] = timestamp.isoformat()
        return self._event_repository.update_event_content_and_metadata(existing.id, content, merged, title=title, timestamp=timestamp) or existing

    def dedupe_browser_pages(self) -> dict[str, int]:
        groups: dict[str, list[Event]] = defaultdict(list)
        for event in self._event_repository.list_all_events(include_hidden=True):
            if event.source.value == "browser_extension" and event.type == "browser_page_captured":
                hash_value = event.metadata.get("normalized_url_hash")
                if isinstance(hash_value, str) and hash_value:
                    groups[hash_value].append(event)
        groups_found = 0
        events_deleted = 0
        events_updated = 0
        for events in groups.values():
            if len(events) < 2:
                continue
            groups_found += 1
            keep = sorted(events, key=self._dedupe_rank, reverse=True)[0]
            duplicates = [event for event in events if event.id != keep.id]
            merged = self._merge_duplicate_metadata(keep, duplicates)
            self._event_repository.update_event_content_and_metadata(keep.id, keep.content, merged, title=keep.title)
            deleted_ids = [event.id for event in duplicates]
            self._relationship_repository.delete_relationships_for_event_ids(deleted_ids)
            for event_id in deleted_ids:
                embedding_index_service.delete_event_vector(event_id)
            events_deleted += self._event_repository.delete_events_by_ids(deleted_ids)
            events_updated += 1
            embedding_index_service.index_event(keep)
        return {"groups_found": groups_found, "events_deleted": events_deleted, "events_updated": events_updated}

    def fix_browser_content_quality(self) -> dict[str, int]:
        updated = 0
        for event in self._event_repository.list_all_events(include_hidden=True):
            if event.source.value != "browser_extension" or event.type != "browser_page_captured":
                continue
            quality = content_quality_from_capture(event.content, event.metadata)
            metadata = dict(event.metadata)
            changed = False
            for key in ["text_excerpt_included", "captured_text_chars", "page_context_missing", "content_quality", "summary_status", "summary_method"]:
                if metadata.get(key) != quality[key]:
                    metadata[key] = quality[key]
                    changed = True
            if not changed:
                continue
            refreshed = self._event_repository.update_event_content_and_metadata(event.id, event.content, metadata, title=event.title) or event
            if refreshed.is_indexable:
                embedding_index_service.index_event(refreshed)
            updated += 1
        return {"updated": updated}

    def _browser_metadata(self, metadata: dict[str, Any], content: str, config: dict[str, Any]) -> dict[str, Any]:
        metadata = self._url_identity(metadata)
        metadata.setdefault("ignored_domains", config.get("ignored_domains", []))
        metadata.setdefault("important_domains", config.get("important_domains", []))
        title = str(metadata.get("page_title") or "")
        page_type = classify_url_page_type(str(metadata.get("url") or ""), title, metadata)
        importance = browser_importance_service.classify_browser_page(str(metadata.get("url") or ""), title, content[:1000], metadata)
        metadata["page_type"] = metadata.get("page_type") or page_type["page_type"]
        metadata["page_type_reason"] = page_type["reason"]
        metadata["importance"] = importance.importance
        metadata["importance_reason"] = importance.reason
        metadata["category"] = importance.category
        if importance.importance == "private":
            raise PermissionError("Browser page blocked by privacy rules.")
        if importance.importance in {"normal", "noisy"} and not bool(metadata.get("manual_capture")):
            raise PermissionError("Browser page is not important enough for visible capture.")
        metadata.update({key: value for key, value in content_quality_from_capture(content, metadata).items() if key not in {"extracted_text", "meaningful"}})
        if metadata["page_type"] in {"homepage", "listing"} and not bool(metadata.get("manual_capture")):
            raise PermissionError("Browser listing/home pages are stored only as hidden history.")
        return metadata

    def _url_identity(self, metadata: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(metadata)
        normalized = normalize_url(str(metadata.get("url") or ""))
        metadata["normalized_url"] = normalized
        metadata["normalized_url_hash"] = url_hash(normalized)
        return metadata

    def _prepare_capture_content(self, title: str, content: str, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        metadata.update({key: value for key, value in content_quality_from_capture(content, metadata).items() if key not in {"extracted_text", "meaningful"}})
        return (content, metadata)

    def _is_better_content(
        self,
        new_content: str,
        old_content: str,
        metadata: dict[str, Any],
        existing_metadata: dict[str, Any] | None = None,
    ) -> bool:
        existing_metadata = existing_metadata or {}
        existing_is_title_only = (
            bool(existing_metadata.get("page_context_missing"))
            or str(existing_metadata.get("content_quality") or "") == "title_only"
            or int(existing_metadata.get("captured_text_chars") or 0) == 0
        )
        new_has_context = not bool(metadata.get("page_context_missing")) and int(metadata.get("captured_text_chars") or 0) > 120
        if existing_is_title_only and new_has_context:
            return True
        return len(new_content) > len(old_content) + 300

    def _safe_relationships(self, event: Event) -> None:
        try:
            relationship_service.detect_relationships_for_event(event)
        except Exception:
            pass

    def _dedupe_rank(self, event: Event) -> tuple[int, int, str]:
        ready = 1 if event.metadata.get("summary_status") == "ready" else 0
        last_seen = str(event.metadata.get("last_seen_at") or event.timestamp.isoformat())
        return (ready, len(event.content), last_seen)

    def _merge_duplicate_metadata(self, keep: Event, duplicates: list[Event]) -> dict[str, Any]:
        metadata = dict(keep.metadata)
        all_events = [keep, *duplicates]
        metadata["visit_count"] = sum(int(event.metadata.get("visit_count") or 1) for event in all_events)
        metadata["first_seen_at"] = min(str(event.metadata.get("first_seen_at") or event.timestamp.isoformat()) for event in all_events)
        metadata["last_seen_at"] = max(str(event.metadata.get("last_seen_at") or event.timestamp.isoformat()) for event in all_events)
        return metadata


browser_memory_service = BrowserMemoryService()
