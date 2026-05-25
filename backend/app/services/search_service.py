import json
import re
from datetime import datetime, timezone

from app.core.dependencies import get_event_repository
from app.domain.models import Event
from app.repositories.base import EventRepository
from app.schemas.search import SearchResponse, SearchResult, SearchStatsResponse
from app.services.memory_classifier import get_memory_category, is_hidden_from_default_memory
from app.services.embedding_index_service import embedding_index_service
from app.services.relationship_service import relationship_service

STOP_WORDS = {"a", "the", "to", "of", "in", "and", "or", "for", "with"}


class SearchService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()

    def search_events(
        self,
        query: str,
        sources: list[str] | None = None,
        category: str | None = None,
        limit: int = 10,
        include_hidden: bool = True,
        search_mode: str | None = "auto",
    ) -> SearchResponse:
        requested_mode = (search_mode or "auto").lower()
        if requested_mode not in {"keyword", "semantic", "hybrid", "auto"}:
            requested_mode = "auto"

        if requested_mode == "keyword":
            return self._keyword_search(query, sources, category, limit, include_hidden, requested_mode)

        semantic_available = embedding_index_service.embeddings_available()
        if requested_mode in {"semantic", "hybrid"} and not semantic_available:
            response = self._keyword_search(query, sources, category, limit, include_hidden, requested_mode)
            response.warning = merge_warning(response.warning, "Semantic search unavailable. Falling back to keyword search.")
            response.requested_search_mode = requested_mode
            return response

        if requested_mode == "semantic":
            return self._semantic_search(query, sources, category, limit, include_hidden, requested_mode)

        if requested_mode == "hybrid" or semantic_available:
            return self._hybrid_search(query, sources, category, limit, include_hidden, requested_mode)

        return self._keyword_search(query, sources, category, limit, include_hidden, requested_mode)

    def _keyword_search(
        self,
        query: str,
        sources: list[str] | None,
        category: str | None,
        limit: int,
        include_hidden: bool,
        requested_mode: str | None = "keyword",
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
            requested_search_mode=requested_mode,
            warning=warning,
        )

    def _semantic_search(
        self,
        query: str,
        sources: list[str] | None,
        category: str | None,
        limit: int,
        include_hidden: bool,
        requested_mode: str | None = "semantic",
    ) -> SearchResponse:
        try:
            vector_rows = embedding_index_service.semantic_search(
                query=query,
                limit=limit,
                sources=sources,
                category=category,
                include_hidden=include_hidden,
            )
        except Exception as exc:
            response = self._keyword_search(query, sources, category, limit, include_hidden, requested_mode)
            response.warning = merge_warning(response.warning, f"Semantic search failed. Falling back to keyword search: {exc}")
            return response

        results: list[SearchResult] = []
        for row in vector_rows:
            event = self._event_repository.get_event_by_id(row["event_id"])
            if event is None:
                continue
            results.append(self._to_search_result(event, raw_score=row["score"], max_score=1, match_reason="Semantic match"))
        return SearchResponse(
            query=query,
            results=results,
            total=len(results),
            search_mode="semantic",
            requested_search_mode=requested_mode,
            warning=None,
        )

    def _hybrid_search(
        self,
        query: str,
        sources: list[str] | None,
        category: str | None,
        limit: int,
        include_hidden: bool,
        requested_mode: str | None = "hybrid",
    ) -> SearchResponse:
        keyword_response = self._keyword_search(query, sources, category, limit, include_hidden, requested_mode)
        semantic_response = self._semantic_search(query, sources, category, limit, include_hidden, requested_mode)
        if semantic_response.search_mode != "semantic":
            semantic_response.requested_search_mode = requested_mode
            return semantic_response

        merged: dict[str, dict] = {}
        for result in keyword_response.results:
            merged[result.event_id] = {"event_id": result.event_id, "keyword": result.score, "semantic": 0.0}
        for result in semantic_response.results:
            row = merged.setdefault(result.event_id, {"event_id": result.event_id, "keyword": 0.0, "semantic": 0.0})
            row["semantic"] = result.score

        scored = sorted(
            (
                (row["semantic"] * 0.65 + row["keyword"] * 0.35, row["event_id"])
                for row in merged.values()
            ),
            reverse=True,
        )[:limit]
        results: list[SearchResult] = []
        for score, event_id in scored:
            event = self._event_repository.get_event_by_id(event_id)
            if event is None:
                continue
            reason = "Semantic + keyword match" if merged[event_id]["keyword"] and merged[event_id]["semantic"] else "Semantic match" if merged[event_id]["semantic"] else "Keyword match"
            results.append(self._to_search_result(event, raw_score=score, max_score=1, match_reason=reason))
        return SearchResponse(
            query=query,
            results=results,
            total=len(results),
            search_mode="hybrid",
            requested_search_mode=requested_mode,
            warning=keyword_response.warning,
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
        normalized_score = round(min(raw_score / max_score, 1.0), 4) if max_score else 0.0
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
            related_count=relationship_service.related_count(event.id),
            related_preview=[
                {
                    "event_id": item["event"].id,
                    "source": item["event"].source.value,
                    "type": item["event"].type,
                    "title": item["event"].title,
                    "content_preview": item["event"].content[:180],
                    "relationship_type": item["relationship"].relationship_type,
                    "strength": item["relationship"].strength,
                    "reason": item["relationship"].reason,
                }
                for item in relationship_service.get_related_context(event.id, limit=3)
            ],
        )


def merge_warning(existing: str | None, addition: str) -> str:
    return f"{existing} {addition}" if existing else addition
