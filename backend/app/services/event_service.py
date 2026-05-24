from app.domain.models import Event
from app.repositories.memory_event_repository import MemoryEventRepository, get_memory_event_repository
from app.schemas.events import EventResponse
from app.services.memory_classifier import get_memory_category, is_hidden_from_default_memory


class EventService:
    def __init__(self, event_repository: MemoryEventRepository | None = None) -> None:
        self._event_repository = event_repository or get_memory_event_repository()

    def list_recent_events(
        self,
        source: str | None = None,
        category: str | None = None,
        limit: int = 20,
        include_hidden: bool = False,
    ) -> list[Event]:
        safe_limit = max(1, min(limit, 100))
        events = self._event_repository.list_all_events()
        filtered = [
            event
            for event in events
            if self._matches_filters(event=event, source=source, category=category, include_hidden=include_hidden)
        ]
        filtered.sort(key=lambda event: event.timestamp, reverse=True)
        return filtered[:safe_limit]

    def get_event_by_id(self, event_id: str) -> Event | None:
        return self._event_repository.get_event_by_id(event_id)

    def to_event_response(self, event: Event) -> EventResponse:
        payload = event.model_dump()
        payload["memory_category"] = get_memory_category(event)
        payload["hidden_from_default"] = is_hidden_from_default_memory(event)
        return EventResponse(**payload)

    def count_events(self) -> int:
        return self._event_repository.count_events()

    def count_by_source(self) -> dict[str, int]:
        return self._event_repository.count_by_source()

    def _matches_filters(
        self,
        *,
        event: Event,
        source: str | None,
        category: str | None,
        include_hidden: bool,
    ) -> bool:
        if source and event.source.value != source:
            return False

        event_category = get_memory_category(event)
        if category and event_category != category:
            return False

        if is_hidden_from_default_memory(event) and not include_hidden:
            return category == "chat"

        if category == "mindos" and event_category == "chat" and not include_hidden:
            return False

        return True
