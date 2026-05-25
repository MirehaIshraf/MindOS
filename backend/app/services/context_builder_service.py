from collections import Counter, defaultdict

from app.core.dependencies import get_event_repository, get_relationship_repository
from app.domain.models import Event, Relationship
from app.repositories.base import EventRepository, RelationshipRepository
from app.schemas.context import ContextEvent, ContextPackage, ContextRelationship, ContextSourceGroup
from app.services.memory_classifier import get_memory_category, is_hidden_from_default_memory
from app.services.search_service import SearchService

MAX_EVENT_CONTENT_CHARS = 1200
MAX_CONTEXT_TOKENS = 4000


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
        limit: int = 5,
        related_per_event: int = 2,
        include_hidden: bool = True,
    ) -> ContextPackage:
        return self._build_from_query(
            query=query,
            limit=limit,
            related_per_event=related_per_event,
            include_hidden=include_hidden,
        )

    def build_task_context(self, instruction: str, limit: int = 5, related_per_event: int = 2) -> ContextPackage:
        return self._build_from_query(
            query=instruction,
            limit=limit,
            related_per_event=related_per_event,
            include_hidden=True,
        )

    def get_context_for_event(self, event_id: str, related_limit: int = 10) -> ContextPackage:
        event = self._event_repository.get_event_by_id(event_id)
        if event is None:
            raise KeyError("Event not found.")

        direct = [self._to_context_event(event, score=None, match_reason="Selected memory event")]
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
                    f"Content: {event.content}",
                    "",
                ]
            )

        lines.extend(["# Source Summary", context_package.summary, ""])
        if context_package.warnings:
            lines.extend(["# Warnings", *context_package.warnings])
        return "\n".join(lines).strip()

    def _build_from_query(self, query: str, limit: int, related_per_event: int, include_hidden: bool) -> ContextPackage:
        search_response = self._search_service.search_events(
            query=query,
            sources=None,
            limit=limit,
            include_hidden=include_hidden,
        )
        direct_events: list[ContextEvent] = []
        related_events: list[ContextEvent] = []
        relationships: list[ContextRelationship] = []
        direct_ids: set[str] = set()
        seen_related: set[str] = set()

        for result in search_response.results:
            event = self._event_repository.get_event_by_id(result.event_id)
            if event is None:
                continue
            direct_ids.add(event.id)
            direct_events.append(
                self._to_context_event(
                    event,
                    score=result.score,
                    match_reason=result.match_reason,
                )
            )

        for direct in direct_events:
            for item in self._relationship_repository.get_related_events(direct.event_id, limit=related_per_event):
                event = item["event"]
                relationship = item["relationship"]
                if event.id in direct_ids or event.id in seen_related:
                    continue
                seen_related.add(event.id)
                related_events.append(
                    self._to_context_event(
                        event,
                        score=relationship.strength,
                        match_reason=f"{relationship.relationship_type}: {relationship.reason}",
                    )
                )
                relationships.append(self._to_context_relationship(relationship))

        package = self._package(
            query=query,
            direct_events=direct_events,
            related_events=related_events,
            relationships=relationships,
            warnings=[search_response.warning] if search_response.warning else [],
        )
        return self._trim_package(package)

    def _package(
        self,
        *,
        query: str,
        direct_events: list[ContextEvent],
        related_events: list[ContextEvent],
        relationships: list[ContextRelationship],
        warnings: list[str] | None = None,
    ) -> ContextPackage:
        source_groups = self._source_groups([*direct_events, *related_events])
        summary = self._summary(direct_events, related_events, relationships, source_groups)
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
        )

    def _trim_package(self, package: ContextPackage) -> ContextPackage:
        if package.token_estimate <= MAX_CONTEXT_TOKENS:
            return package

        trimmed_related = [
            event.model_copy(update={"content": event.content[:600], "content_preview": event.content[:180]})
            for event in package.related_events
        ]
        rebuilt = self._package(
            query=package.query,
            direct_events=package.direct_events,
            related_events=trimmed_related,
            relationships=package.relationships,
            warnings=[*package.warnings, "Context was trimmed to fit size limits."],
        )
        return rebuilt

    def _to_context_event(self, event: Event, score: float | None, match_reason: str | None) -> ContextEvent:
        content = event.content[:MAX_EVENT_CONTENT_CHARS]
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
        direct_events: list[ContextEvent],
        related_events: list[ContextEvent],
        relationships: list[ContextRelationship],
        source_groups: list[ContextSourceGroup],
    ) -> str:
        sources = ", ".join(group.source for group in source_groups[:4]) or "none"
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


context_builder_service = ContextBuilderService()
