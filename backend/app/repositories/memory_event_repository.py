from typing import Any

from app.domain.enums import EmbeddingStatus
from app.domain.models import Event
from app.repositories.base import EventRepository


class MemoryEventRepository(EventRepository):
    def __init__(self) -> None:
        self._events: dict[str, Event] = {}

    def create_event(self, event_data: dict[str, Any]) -> Event:
        event = Event(**event_data)
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
        return sorted(events, key=lambda event: event.timestamp, reverse=True)[:limit]

    def list_all_events(self, include_hidden: bool = True) -> list[Event]:
        return list(self._events.values())

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

    def clear_events(self) -> None:
        self._events.clear()

    def delete_events_by_source(self, source: str) -> int:
        event_ids = [event_id for event_id, event in self._events.items() if event.source.value == source]
        for event_id in event_ids:
            del self._events[event_id]
        return len(event_ids)

    def _try_index_event(self, event: Event) -> None:
        try:
            from app.services.embedding_index_service import embedding_index_service

            embedding_index_service.index_event(event)
        except Exception:
            pass


memory_event_repository = MemoryEventRepository()


def get_memory_event_repository() -> MemoryEventRepository:
    return memory_event_repository
