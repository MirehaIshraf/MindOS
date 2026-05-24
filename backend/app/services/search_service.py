import json
import re
from datetime import datetime, timezone

from app.domain.models import Event
from app.repositories.memory_event_repository import MemoryEventRepository, get_memory_event_repository
from app.schemas.search import SearchResponse, SearchResult, SearchStatsResponse
from app.services.memory_classifier import get_memory_category, is_hidden_from_default_memory

STOP_WORDS = {"a", "the", "to", "of", "in", "and", "or", "for", "with"}


class SearchService:
    def __init__(self, event_repository: MemoryEventRepository | None = None) -> None:
        self._event_repository = event_repository or get_memory_event_repository()

    def search_events(
        self,
        query: str,
        sources: list[str] | None = None,
        category: str | None = None,
        limit: int = 10,
        include_hidden: bool = True,
    ) -> SearchResponse:
        normalized_query = query.strip().lower()
        tokens = self._tokenize(normalized_query)
        allowed_sources = {source.lower() for source in sources} if sources else None
        scored_results: list[tuple[float, Event, str]] = []

        for event in self._event_repository.list_all_events():
            if allowed_sources and event.source.value not in allowed_sources:
                continue
            if category and get_memory_category(event) != category:
                continue
            if is_hidden_from_default_memory(event) and not include_hidden:
                continue

            raw_score, match_reason = self._score_event(event, normalized_query, tokens)
            if raw_score > 0:
                scored_results.append((raw_score, event, match_reason))

        scored_results.sort(key=lambda item: (item[0], item[1].timestamp), reverse=True)
        limited_results = scored_results[:limit]
        max_score = max((score for score, _, _ in limited_results), default=1)

        results = [
            self._to_search_result(event=event, raw_score=score, max_score=max_score, match_reason=match_reason)
            for score, event, match_reason in limited_results
        ]

        warning = None
        if not tokens:
            warning = "Query only contained ignored common words."

        return SearchResponse(
            query=query,
            results=results,
            total=len(results),
            search_mode="keyword",
            warning=warning,
        )

    def get_search_stats(self) -> SearchStatsResponse:
        events = self._event_repository.list_all_events()
        last_ingested_at = max((event.created_at for event in events), default=None)
        by_category: dict[str, int] = {}
        hidden_events = 0
        for event in events:
            category = get_memory_category(event)
            by_category[category] = by_category.get(category, 0) + 1
            if is_hidden_from_default_memory(event):
                hidden_events += 1
        return SearchStatsResponse(
            total_events=self._event_repository.count_events(),
            visible_default_events=max(len(events) - hidden_events, 0),
            hidden_events=hidden_events,
            by_source=self._event_repository.count_by_source(),
            by_category=by_category,
            last_ingested_at=last_ingested_at,
        )

    def get_event_detail(self, event_id: str) -> Event | None:
        return self._event_repository.get_event_by_id(event_id)

    def _tokenize(self, normalized_query: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9_]+", normalized_query) if token not in STOP_WORDS and len(token) > 1]

    def _score_event(self, event: Event, normalized_query: str, tokens: list[str]) -> tuple[float, str]:
        title = event.title.lower()
        content = event.content.lower()
        event_type = event.type.lower()
        source = event.source.value.lower()
        metadata = json.dumps(event.metadata, sort_keys=True).lower()
        score = 0.0
        matched_title = False
        matched_content = False
        matched_metadata = False
        matched_source_type = False

        if normalized_query and normalized_query in title:
            score += 50
            matched_title = True
        if normalized_query and normalized_query in content:
            score += 35
            matched_content = True

        for token in tokens:
            if token in title:
                score += 10
                matched_title = True
            if token in content:
                score += 5
                matched_content = True
            if token in event_type:
                score += 4
                matched_source_type = True
            if token in source:
                score += 3
                matched_source_type = True
            if token in metadata:
                score += 2
                matched_metadata = True

        if score > 0:
            score += self._recency_bonus(event)

        return score, self._match_reason(
            matched_title=matched_title,
            matched_content=matched_content,
            matched_metadata=matched_metadata,
            matched_source_type=matched_source_type,
            score=score,
        )

    def _recency_bonus(self, event: Event) -> float:
        now = datetime.now(timezone.utc)
        event_time = event.timestamp
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)

        age_hours = max((now - event_time).total_seconds() / 3600, 0)
        return max(0.0, 5.0 - min(age_hours / 24, 5.0))

    def _match_reason(
        self,
        *,
        matched_title: bool,
        matched_content: bool,
        matched_metadata: bool,
        matched_source_type: bool,
        score: float,
    ) -> str:
        if matched_title and matched_content:
            return "Matched title and content"
        if matched_title:
            return "Matched title"
        if matched_content:
            return "Matched content"
        if matched_metadata:
            return "Matched metadata"
        if matched_source_type:
            return "Matched source/type"
        if score > 0:
            return "Recent related event"
        return "No match"

    def _to_search_result(self, event: Event, raw_score: float, max_score: float, match_reason: str) -> SearchResult:
        normalized_score = round(min(raw_score / max_score, 1.0), 4)
        return SearchResult(
            event_id=event.id,
            source=event.source.value,
            type=event.type,
            title=event.title,
            content_preview=event.content[:180],
            metadata=event.metadata,
            timestamp=event.timestamp,
            created_at=event.created_at,
            embedding_status=event.embedding_status.value,
            memory_category=get_memory_category(event),
            hidden_from_default=is_hidden_from_default_memory(event),
            score=normalized_score,
            match_reason=match_reason,
        )
