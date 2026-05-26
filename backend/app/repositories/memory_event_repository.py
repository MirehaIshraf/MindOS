from typing import Any

from app.domain.enums import EmbeddingStatus
from app.domain.models import Event
from app.repositories.base import EventRepository
from app.services.memory_policy_service import apply_memory_policy


class MemoryEventRepository(EventRepository):
    def __init__(self) -> None:
        self._events: dict[str, Event] = {}

    def create_event(self, event_data: dict[str, Any]) -> Event:
        event = Event(**apply_memory_policy(event_data))
        self._events[event.id] = event
        self._try_index_event(event)
        return event

    def create_events(self, list_of_event_data: list[dict[str, Any]]) -> list[Event]:
        return [self.create_event(event_data) for event_data in list_of_event_data]

    def get_event_by_id(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def list_recent_events(
        self,
        source: str | None = None,
        category: str | None = None,
        limit: int = 20,
        include_hidden: bool = False,
    ) -> list[Event]:
        events = list(self._events.values())
        if source:
            events = [event for event in events if event.source.value == source]
        if category:
            events = [event for event in events if event.memory_category == category]
        if not include_hidden:
            events = [event for event in events if not event.hidden_from_default or category == "chat"]
        return sorted(events, key=lambda event: event.timestamp, reverse=True)[:limit]

    def list_all_events(self, include_hidden: bool = True) -> list[Event]:
        events = list(self._events.values())
        return events if include_hidden else [event for event in events if not event.hidden_from_default]

    def count_events(self) -> int:
        return len(self._events)

    def count_by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._events.values():
            source = event.source.value
            counts[source] = counts.get(source, 0) + 1
        return counts

    def count_by_embedding_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._events.values():
            status = event.embedding_status.value
            counts[status] = counts.get(status, 0) + 1
        return counts

    def update_embedding_status(self, event_id: str, status: str) -> None:
        event = self._events.get(event_id)
        if event is None:
            return
        self._events[event_id] = event.model_copy(update={"embedding_status": EmbeddingStatus(status)})

    def list_events_for_embedding(self, limit: int | None = None) -> list[Event]:
        events = sorted(self._events.values(), key=lambda event: event.created_at)
        return events if limit is None else events[:limit]

    def update_event_policy(self, event_id: str, policy: dict) -> None:
        event = self._events.get(event_id)
        if event is None:
            return
        updates = {
            "memory_category": policy["memory_category"],
            "hidden_from_default": policy["hidden_from_default"],
            "is_indexable": policy["is_indexable"],
            "is_relationship_eligible": policy["is_relationship_eligible"],
            "is_context_eligible": policy["is_context_eligible"],
        }
        if not policy["is_indexable"]:
            updates["embedding_status"] = EmbeddingStatus.not_required
        self._events[event_id] = event.model_copy(update=updates)

    def count_policy_eligibility(self) -> dict[str, int]:
        events = list(self._events.values())
        return {
            "total_events": len(events),
            "indexable_events": sum(1 for event in events if event.is_indexable),
            "non_indexable_events": sum(1 for event in events if not event.is_indexable),
            "relationship_eligible_events": sum(1 for event in events if event.is_relationship_eligible),
            "context_eligible_events": sum(1 for event in events if event.is_context_eligible),
            "hidden_events": sum(1 for event in events if event.hidden_from_default),
        }

    def clear_events(self) -> None:
        self._events.clear()

    def delete_events_by_source(self, source: str) -> int:
        event_ids = [event_id for event_id, event in self._events.items() if event.source.value == source]
        for event_id in event_ids:
            del self._events[event_id]
        return len(event_ids)

    def delete_events_by_ids(self, event_ids: list[str]) -> int:
        deleted = 0
        for event_id in event_ids:
            if event_id in self._events:
                del self._events[event_id]
                deleted += 1
        return deleted

    def _try_index_event(self, event: Event) -> None:
        try:
            from app.services.embedding_index_service import embedding_index_service

            embedding_index_service.index_event(event)
        except Exception:
            pass


memory_event_repository = MemoryEventRepository()


def get_memory_event_repository() -> MemoryEventRepository:
    return memory_event_repository
