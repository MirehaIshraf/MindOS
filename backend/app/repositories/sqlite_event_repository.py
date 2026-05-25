from typing import Any

from sqlalchemy import delete, func, select

from app.core.database import EventRecord, get_session_factory, initialize_database
from app.domain.enums import EmbeddingStatus, EventSource
from app.domain.models import Event
from app.repositories.base import EventRepository
from app.repositories.sqlite_utils import dumps_json, loads_json
from app.services.memory_classifier import get_memory_category, is_hidden_from_default_memory


class SQLiteEventRepository(EventRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

    def create_event(self, event_data: dict[str, Any]) -> Event:
        event = Event(**event_data)
        with self._session_factory() as session:
            session.add(self._to_record(event))
            session.commit()
        return event

    def create_events(self, list_of_event_data: list[dict[str, Any]]) -> list[Event]:
        events = [Event(**event_data) for event_data in list_of_event_data]
        with self._session_factory() as session:
            session.add_all([self._to_record(event) for event in events])
            session.commit()
        return events

    def get_event_by_id(self, event_id: str) -> Event | None:
        with self._session_factory() as session:
            record = session.get(EventRecord, event_id)
            return self._to_event(record) if record else None

    def list_recent_events(
        self,
        source: str | None = None,
        category: str | None = None,
        limit: int = 20,
        include_hidden: bool = False,
    ) -> list[Event]:
        events = self.list_all_events(include_hidden=True)
        filtered = [
            event
            for event in events
            if self._matches_filters(event=event, source=source, category=category, include_hidden=include_hidden)
        ]
        filtered.sort(key=lambda event: event.timestamp, reverse=True)
        return filtered[: max(1, min(limit, 100))]

    def list_all_events(self, include_hidden: bool = True) -> list[Event]:
        with self._session_factory() as session:
            records = session.scalars(select(EventRecord).order_by(EventRecord.timestamp.desc())).all()
            events = [self._to_event(record) for record in records]
        if include_hidden:
            return events
        return [event for event in events if not is_hidden_from_default_memory(event)]

    def count_events(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(EventRecord)) or 0)

    def count_by_source(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = session.execute(select(EventRecord.source, func.count()).group_by(EventRecord.source)).all()
        return {str(source): int(count) for source, count in rows}

    def clear_events(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(EventRecord))
            session.commit()

    def delete_events_by_source(self, source: str) -> int:
        with self._session_factory() as session:
            result = session.execute(delete(EventRecord).where(EventRecord.source == source))
            session.commit()
            return int(result.rowcount or 0)

    def _to_record(self, event: Event) -> EventRecord:
        category = get_memory_category(event)
        hidden = is_hidden_from_default_memory(event)
        return EventRecord(
            id=event.id,
            source=event.source.value,
            type=event.type,
            title=event.title,
            content=event.content,
            metadata_json=dumps_json(event.metadata),
            timestamp=event.timestamp,
            created_at=event.created_at,
            embedding_status=event.embedding_status.value,
            memory_category=category,
            hidden_from_default=hidden,
        )

    def _to_event(self, record: EventRecord) -> Event:
        return Event(
            id=record.id,
            source=EventSource(record.source),
            type=record.type,
            title=record.title,
            content=record.content or "",
            metadata=loads_json(record.metadata_json, {}),
            timestamp=record.timestamp,
            created_at=record.created_at,
            embedding_status=EmbeddingStatus(record.embedding_status),
        )

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
        return True
