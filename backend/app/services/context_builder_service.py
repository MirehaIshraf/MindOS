from collections import Counter, defaultdict
from typing import Any

from app.core.config import get_settings
from app.core.dependencies import get_event_repository, get_relationship_repository
from app.domain.models import Event, Relationship
from app.repositories.base import EventRepository, RelationshipRepository
from app.schemas.context import ContextEvent, ContextPackage, ContextRelationship, ContextSourceGroup, QueryIntent
from app.services.memory_classifier import get_memory_category, is_hidden_from_default_memory
from app.services.search_service import SearchService

HIGH_PRIORITY_RELATIONSHIPS = {"FIXED_BY", "CAUSED_BY", "SAME_TASK", "SAME_FILE", "MENTIONS"}
MEDIUM_PRIORITY_RELATIONSHIPS = {"SAME_REPO"}
LOW_PRIORITY_RELATIONSHIPS = {"SAME_TOPIC", "TEMPORAL_NEARBY"}
PROFILE_DEFAULTS = {
    "precision_lookup": {
        "direct_limit": 5,
        "related_per_event": 0,
        "direct_chars": 1600,
        "related_chars": 0,
        "max_total_chars": 4500,
        "allow_low_priority": False,
        "expand_relationships": False,
        "min_score": 0.35,
        "search_mode": "hybrid",
    },
    "speed_chat": {
        "direct_limit": 3,
        "related_per_event": 0,
        "direct_chars": 400,
        "related_chars": 200,
        "max_total_chars": 3000,
        "allow_low_priority": False,
        "expand_relationships": False,
        "min_score": None,
        "search_mode": "auto",
    },
    "fast_chat": {
        "direct_limit": 4,
        "related_per_event": 1,
        "direct_chars": 700,
        "related_chars": 400,
        "max_total_chars": 6000,
        "allow_low_priority": False,
        "expand_relationships": True,
        "min_score": None,
        "search_mode": "auto",
    },
    "root_cause": {
        "direct_limit": 5,
        "related_per_event": 1,
        "direct_chars": 900,
        "related_chars": 500,
        "max_total_chars": 7000,
        "allow_low_priority": False,
        "expand_relationships": True,
        "min_score": None,
        "search_mode": "auto",
    },
    "summary": {
        "direct_limit": 10,
        "related_per_event": 1,
        "direct_chars": 900,
        "related_chars": 350,
        "max_total_chars": 9000,
        "allow_low_priority": False,
        "expand_relationships": True,
        "min_score": None,
        "search_mode": "auto",
    },
    "general_chat": {
        "direct_limit": 3,
        "related_per_event": 0,
        "direct_chars": 500,
        "related_chars": 0,
        "max_total_chars": 2500,
        "allow_low_priority": False,
        "expand_relationships": False,
        "min_score": 0.45,
        "search_mode": "hybrid",
    },
    "source_focused": {
        "direct_limit": 3,
        "related_per_event": 0,
        "direct_chars": 2500,
        "related_chars": 400,
        "max_total_chars": 8000,
        "allow_low_priority": False,
        "expand_relationships": False,
        "min_score": None,
        "search_mode": "hybrid",
    },
    "deep_analysis": {
        "direct_limit": 8,
        "related_per_event": 2,
        "direct_chars": 1200,
        "related_chars": 700,
        "max_total_chars": 12000,
        "allow_low_priority": True,
        "expand_relationships": True,
        "min_score": None,
        "search_mode": "auto",
    },
    "deep_chat": {
        "direct_limit": 8,
        "related_per_event": 2,
        "direct_chars": 1000,
        "related_chars": 600,
        "max_total_chars": 10000,
        "allow_low_priority": True,
        "expand_relationships": True,
        "min_score": None,
        "search_mode": "auto",
    },
    "task": {
        "direct_limit": 5,
        "related_per_event": 1,
        "direct_chars": 800,
        "related_chars": 450,
        "max_total_chars": 7000,
        "allow_low_priority": False,
        "expand_relationships": True,
        "min_score": None,
        "search_mode": "auto",
    },
}


class ContextBuilderService:
    def __init__(
        self,
        search_service: SearchService | None = None,
        event_repository: EventRepository | None = None,
        relationship_repository: RelationshipRepository | None = None,
    ) -> None:
        self._event_repository = event_repository or get_event_repository()
        self._relationship_repository = relationship_repository or get_relationship_repository()
        self._search_service = search_service or SearchService(self._event_repository)

    def build_chat_context(
        self,
        query: str,
        limit: int | None = None,
        related_per_event: int | None = None,
        include_hidden: bool = True,
        profile: str = "fast_chat",
        intent: QueryIntent | None = None,
        source_event_ids: list[str] | None = None,
    ) -> ContextPackage:
        settings = get_settings()
        limit = limit or settings.chat_context_direct_limit
        related_per_event = related_per_event if related_per_event is not None else settings.chat_context_related_per_event
        return self._build_from_query(
            query=query,
            limit=limit,
            related_per_event=related_per_event,
            include_hidden=include_hidden,
            profile=profile,
            intent=intent,
            source_event_ids=source_event_ids,
        )

    def build_task_context(self, instruction: str, limit: int = 5, related_per_event: int = 1) -> ContextPackage:
        return self._build_from_query(
            query=instruction,
            limit=limit,
            related_per_event=related_per_event,
            include_hidden=True,
            profile="task",
        )

    def get_context_for_event(self, event_id: str, related_limit: int = 10) -> ContextPackage:
        event = self._event_repository.get_event_by_id(event_id)
        if event is None:
            raise KeyError("Event not found.")

        profile_config = self._profile_config("deep_analysis")
        direct = [self._to_context_event(event, score=None, match_reason="Selected memory event", max_chars=profile_config["direct_chars"])]
        related_events: list[ContextEvent] = []
        relationships: list[ContextRelationship] = []
        seen = {event.id}

        for item in self._relationship_repository.get_related_events(event_id, limit=related_limit):
            related_event = item["event"]
            relationship = item["relationship"]
            if related_event.id in seen:
                continue
            seen.add(related_event.id)
            related_events.append(
                self._to_context_event(
                    related_event,
                    score=relationship.strength,
                    match_reason=f"{relationship.relationship_type}: {relationship.reason}",
                    max_chars=profile_config["related_chars"],
                )
            )
            relationships.append(self._to_context_relationship(relationship))

        return self._package(query=event.title, direct_events=direct, related_events=related_events, relationships=relationships)

    def format_context_for_llm(self, context_package: ContextPackage) -> str:
        lines = [
            "# User Query",
            context_package.query,
            "",
            "# Direct Memory Matches",
        ]
        direct_indexes: dict[str, int] = {}
        for index, event in enumerate(context_package.direct_events, start=1):
            direct_indexes[event.event_id] = index
            lines.extend(
                [
                    f"[{index}] Source: {event.source} | Type: {event.type} | Time: {event.timestamp.isoformat()}",
                    f"Title: {event.title}",
                    *self._metadata_lines(event),
                    f"Content: {event.content}",
                    "",
                ]
            )

        lines.append("# Related Memory")
        start_index = len(context_package.direct_events) + 1
        for offset, event in enumerate(context_package.related_events):
            relationship = self._relationship_for_event(event.event_id, context_package.relationships)
            prefix = f"[{start_index + offset}]"
            if relationship:
                related_to = direct_indexes.get(relationship.from_event_id) or direct_indexes.get(relationship.to_event_id)
                if related_to:
                    prefix += (
                        f" Related to [{related_to}] via {relationship.relationship_type}, "
                        f"strength {relationship.strength:.2f}"
                    )
                else:
                    prefix += f" {relationship.relationship_type}, strength {relationship.strength:.2f}"
            lines.extend(
                [
                    prefix,
                    f"Source: {event.source} | Type: {event.type} | Time: {event.timestamp.isoformat()}",
                    f"Title: {event.title}",
                    *self._metadata_lines(event),
                    f"Content: {event.content}",
                    "",
                ]
            )

        lines.extend(["# Source Summary", context_package.summary, ""])
        if context_package.warnings:
            lines.extend(["# Warnings", *context_package.warnings])
        return "\n".join(lines).strip()

    def _build_from_query(
        self,
        query: str,
        limit: int,
        related_per_event: int,
        include_hidden: bool,
        profile: str,
        intent: QueryIntent | None = None,
        source_event_ids: list[str] | None = None,
    ) -> ContextPackage:
        profile_config = self._profile_config(profile)
        search_query = self._search_query(query, intent)
        preferred_sources = intent.preferred_sources if intent and intent.preferred_sources else None
        direct_events: list[ContextEvent] = []
        related_events: list[ContextEvent] = []
        relationships: list[ContextRelationship] = []
        direct_ids: set[str] = set()
        seen_related: set[str] = set()

        for event_id in source_event_ids or []:
            event = self._event_repository.get_event_by_id(event_id)
            if event is None or event.id in direct_ids:
                continue
            if not event.is_context_eligible and not self._allow_lookup_evidence(event, intent):
                continue
            direct_ids.add(event.id)
            direct_events.append(
                self._to_context_event(
                    event,
                    score=1.0,
                    match_reason="Primary source from previous chat turn",
                    max_chars=profile_config["direct_chars"],
                )
            )

        if profile == "source_focused" and direct_events:
            package = self._package(
                query=query,
                direct_events=direct_events,
                related_events=[],
                relationships=[],
                warnings=[],
                metadata={
                    "intent": intent.model_dump(mode="json") if intent else None,
                    "search_query": search_query,
                    "search_mode": "source_focused",
                    "source_event_ids": source_event_ids or [],
                },
            )
            return self._trim_package(package, profile_config=profile_config)

        search_response = self._search_service.search_events(
            query=search_query,
            sources=preferred_sources,
            limit=max(0, min(limit, profile_config["direct_limit"]) - len(direct_events)),
            include_hidden=include_hidden,
            context_only=profile != "precision_lookup",
            search_mode=str(profile_config.get("search_mode") or "auto"),
            excluded_sources=intent.excluded_sources if intent else None,
            excluded_types=intent.excluded_types if intent else None,
            min_score=profile_config.get("min_score") if isinstance(profile_config.get("min_score"), float) else None,
        )

        for result in search_response.results:
            event = self._event_repository.get_event_by_id(result.event_id)
            if event is None or event.id in direct_ids or (not event.is_context_eligible and not self._allow_lookup_evidence(event, intent)):
                continue
            direct_ids.add(event.id)
            direct_events.append(
                self._to_context_event(
                    event,
                    score=result.score,
                    match_reason=result.match_reason,
                    max_chars=profile_config["direct_chars"],
                )
            )

        effective_related_per_event = min(related_per_event, int(profile_config["related_per_event"]))
        if not bool(profile_config.get("expand_relationships", True)):
            effective_related_per_event = 0
        relationship_types_allowed = set(intent.relationship_types_allowed or []) if intent else set()

        for direct in direct_events:
            related_items = self._prioritized_related_items(
                self._relationship_repository.get_related_events(direct.event_id, limit=20),
                allow_low_priority=profile_config["allow_low_priority"],
                needed=effective_related_per_event,
                relationship_types_allowed=relationship_types_allowed,
            )
            for item in related_items:
                event = item["event"]
                relationship = item["relationship"]
                if event.id in direct_ids or event.id in seen_related or not event.is_context_eligible:
                    continue
                seen_related.add(event.id)
                related_events.append(
                    self._to_context_event(
                        event,
                        score=relationship.strength,
                        match_reason=f"{relationship.relationship_type}: {relationship.reason}",
                        max_chars=profile_config["related_chars"],
                    )
                )
                relationships.append(self._to_context_relationship(relationship))

        direct_events = self._dedupe_browser_context_events(direct_events)
        related_events = self._dedupe_browser_context_events(related_events, exclude_ids={event.event_id for event in direct_events})
        relationships = [
            relationship
            for relationship in relationships
            if any(event.event_id in {relationship.from_event_id, relationship.to_event_id} for event in related_events)
        ]
        package = self._package(
            query=query,
            direct_events=direct_events,
            related_events=related_events,
            relationships=relationships,
            warnings=[search_response.warning] if search_response.warning else [],
            metadata={
                "intent": intent.model_dump(mode="json") if intent else None,
                "search_query": search_query,
                "search_mode": search_response.search_mode,
            },
        )
        return self._trim_package(package, profile_config=profile_config)

    def _dedupe_browser_context_events(
        self,
        events: list[ContextEvent],
        exclude_ids: set[str] | None = None,
    ) -> list[ContextEvent]:
        exclude_ids = exclude_ids or set()
        selected: dict[str, ContextEvent] = {}
        output: list[ContextEvent] = []
        for event in events:
            if event.event_id in exclude_ids:
                continue
            normalized_hash = event.metadata.get("normalized_url_hash") if event.source == "browser_extension" else None
            if not isinstance(normalized_hash, str) or not normalized_hash:
                output.append(event)
                continue
            current = selected.get(normalized_hash)
            if current is None or self._context_event_rank(event) > self._context_event_rank(current):
                selected[normalized_hash] = event
        seen_hashes: set[str] = set()
        deduped: list[ContextEvent] = []
        for event in events:
            normalized_hash = event.metadata.get("normalized_url_hash") if event.source == "browser_extension" else None
            if not isinstance(normalized_hash, str) or not normalized_hash:
                if event.event_id not in exclude_ids:
                    deduped.append(event)
                continue
            if normalized_hash in seen_hashes or selected[normalized_hash].event_id != event.event_id:
                continue
            seen_hashes.add(normalized_hash)
            deduped.append(event)
        return deduped

    def _context_event_rank(self, event: ContextEvent) -> tuple[int, int, str]:
        summary_ready = 1 if event.metadata.get("summary_status") == "ready" else 0
        return (summary_ready, len(event.content), event.timestamp.isoformat())

    def _search_query(self, query: str, intent: QueryIntent | None) -> str:
        if intent and intent.search_terms:
            return intent.search_terms[0]
        return query

    def _allow_lookup_evidence(self, event: Event, intent: QueryIntent | None) -> bool:
        return bool(
            intent
            and intent.intent in {"memory_lookup", "entity_details", "source_summary", "follow_up", "follow_up_summary"}
            and event.source.value == "browser_extension"
            and event.type in {"browser_page_seen", "browser_search_query"}
        )

    def _package(
        self,
        *,
        query: str,
        direct_events: list[ContextEvent],
        related_events: list[ContextEvent],
        relationships: list[ContextRelationship],
        warnings: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextPackage:
        source_groups = self._source_groups([*direct_events, *related_events])
        summary = self._summary(query, direct_events, related_events, relationships, source_groups)
        token_estimate = self._token_estimate(query, summary, [*direct_events, *related_events])
        return ContextPackage(
            query=query,
            direct_events=direct_events,
            related_events=related_events,
            relationships=relationships,
            source_groups=source_groups,
            summary=summary,
            token_estimate=token_estimate,
            warnings=warnings or [],
            metadata=metadata or {},
        )

    def _trim_package(self, package: ContextPackage, profile_config: dict[str, Any]) -> ContextPackage:
        if self._total_chars(package) <= profile_config["max_total_chars"]:
            return package

        trimmed_related = [
            event.model_copy(update={"content": event.content[:200], "content_preview": event.content[:120]})
            for event in package.related_events
        ]
        rebuilt = self._package(
            query=package.query,
            direct_events=package.direct_events,
            related_events=trimmed_related,
            relationships=package.relationships,
            warnings=[*package.warnings, "Context trimmed for speed."],
            metadata=package.metadata,
        )
        if self._total_chars(rebuilt) <= profile_config["max_total_chars"]:
            return rebuilt

        trimmed_direct = [
            event.model_copy(update={"content": event.content[:400], "content_preview": event.content[:160]})
            for event in rebuilt.direct_events
        ]
        return self._package(
            query=rebuilt.query,
            direct_events=trimmed_direct,
            related_events=rebuilt.related_events,
            relationships=rebuilt.relationships,
            warnings=rebuilt.warnings,
            metadata=rebuilt.metadata,
        )

    def _to_context_event(self, event: Event, score: float | None, match_reason: str | None, max_chars: int) -> ContextEvent:
        content = self._context_content_for_event(event)[:max_chars]
        return ContextEvent(
            event_id=event.id,
            source=event.source.value,
            type=event.type,
            title=event.title,
            content_preview=content[:180],
            content=content,
            metadata=event.metadata,
            timestamp=event.timestamp,
            score=score,
            match_reason=match_reason,
            memory_category=get_memory_category(event),
            hidden_from_default=is_hidden_from_default_memory(event),
        )

    def _context_content_for_event(self, event: Event) -> str:
        if event.source.value != "browser_extension" or event.type != "browser_page_captured":
            return event.content
        metadata = event.metadata or {}
        if metadata.get("page_context_missing") is True:
            return f"{event.content}\n\nNote: Page context is missing; only title, URL, and metadata are available."
        if metadata.get("summary_status") == "pending":
            return f"{event.content}\n\nNote: Summary is pending, but the captured readable excerpt above is available."
        return event.content

    def _to_context_relationship(self, relationship: Relationship) -> ContextRelationship:
        return ContextRelationship(
            from_event_id=relationship.from_event_id,
            to_event_id=relationship.to_event_id,
            relationship_type=relationship.relationship_type,
            strength=relationship.strength,
            reason=relationship.reason,
        )

    def _source_groups(self, events: list[ContextEvent]) -> list[ContextSourceGroup]:
        grouped: defaultdict[str, list[str]] = defaultdict(list)
        for event in events:
            grouped[event.source].append(event.event_id)
        return [
            ContextSourceGroup(source=source, count=len(event_ids), event_ids=event_ids)
            for source, event_ids in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
        ]

    def _summary(
        self,
        query: str,
        direct_events: list[ContextEvent],
        related_events: list[ContextEvent],
        relationships: list[ContextRelationship],
        source_groups: list[ContextSourceGroup],
    ) -> str:
        sources = ", ".join(group.source for group in source_groups[:4]) or "none"
        if not related_events and not relationships:
            return f"Found {len(direct_events)} precise memory matches for: {query}. Sources: {sources}."
        relationship_types = Counter(relationship.relationship_type for relationship in relationships)
        strongest = ", ".join(kind for kind, _ in relationship_types.most_common(3)) or "none"
        return (
            f"Found {len(direct_events)} direct memory items and {len(related_events)} related items. "
            f"Main sources: {sources}. Strongest relationships: {strongest}."
        )

    def _token_estimate(self, query: str, summary: str, events: list[ContextEvent]) -> int:
        text = query + "\n" + summary + "\n" + "\n".join(f"{event.title}\n{event.content}" for event in events)
        return max(1, round(len(text) / 4))

    def _relationship_for_event(
        self,
        event_id: str,
        relationships: list[ContextRelationship],
    ) -> ContextRelationship | None:
        for relationship in relationships:
            if relationship.from_event_id == event_id or relationship.to_event_id == event_id:
                return relationship
        return None

    def _prioritized_related_items(
        self,
        items: list[dict],
        allow_low_priority: bool,
        needed: int,
        relationship_types_allowed: set[str] | None = None,
    ) -> list[dict]:
        if needed <= 0:
            return []
        if relationship_types_allowed:
            items = [item for item in items if item["relationship"].relationship_type in relationship_types_allowed]

        high = self._sort_related([item for item in items if item["relationship"].relationship_type in HIGH_PRIORITY_RELATIONSHIPS])
        medium = self._sort_related([item for item in items if item["relationship"].relationship_type in MEDIUM_PRIORITY_RELATIONSHIPS])
        low = self._sort_related([item for item in items if item["relationship"].relationship_type in LOW_PRIORITY_RELATIONSHIPS])

        selected = high[:needed]
        if len(selected) < needed:
            selected.extend(medium[: needed - len(selected)])
        if len(selected) < needed and (allow_low_priority or not selected):
            selected.extend(low[: needed - len(selected)])
        return selected[:needed]

    def _sort_related(self, items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda item: item["relationship"].strength, reverse=True)

    def _profile_config(self, profile: str) -> dict[str, Any]:
        config = dict(PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS["fast_chat"]))
        settings = get_settings()
        if profile == "fast_chat":
            config["direct_limit"] = settings.chat_context_direct_limit
            config["related_per_event"] = settings.chat_context_related_per_event
            config["direct_chars"] = settings.chat_context_max_chars_per_event
            config["max_total_chars"] = settings.chat_context_max_total_chars
        return config

    def _metadata_lines(self, event: ContextEvent) -> list[str]:
        metadata = event.metadata or {}
        lines: list[str] = []
        url = metadata.get("url")
        if isinstance(url, str) and url:
            lines.append(f"URL: {url}")
        page_title = metadata.get("page_title")
        if isinstance(page_title, str) and page_title and page_title != event.title:
            lines.append(f"Page title: {page_title}")
        domain = metadata.get("domain")
        if isinstance(domain, str) and domain:
            lines.append(f"Domain: {domain}")
        category = metadata.get("category")
        if isinstance(category, str) and category:
            lines.append(f"Category: {category}")
        importance_reason = metadata.get("importance_reason")
        if isinstance(importance_reason, str) and importance_reason:
            lines.append(f"Importance: {importance_reason}")
        page_type = metadata.get("page_type")
        if isinstance(page_type, str) and page_type:
            lines.append(f"Page type: {page_type}")
        summary_status = metadata.get("summary_status")
        if isinstance(summary_status, str) and summary_status:
            lines.append(f"Summary status: {summary_status}")
        path = metadata.get("file_path") or metadata.get("path") or metadata.get("relative_path") or metadata.get("repo_path")
        if isinstance(path, str) and path:
            lines.append(f"Path: {path}")
        return lines

    def _total_chars(self, package: ContextPackage) -> int:
        return len(self.format_context_for_llm(package))


context_builder_service = ContextBuilderService()
