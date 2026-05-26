from typing import Any

from sqlalchemy import delete, func, select

from app.core.database import EventRecord, get_session_factory, initialize_database
from app.domain.enums import EmbeddingStatus, EventSource
from app.domain.models import Event
from app.repositories.base import EventRepository
from app.repositories.sqlite_utils import dumps_json, loads_json
from app.services.memory_policy_service import apply_memory_policy


class SQLiteEventRepository(EventRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

    def create_event(self, event_data: dict[str, Any]) -> Event:
        event = Event(**apply_memory_policy(event_data))
        with self._session_factory() as session:
            session.add(self._to_record(event))
            session.commit()
        self._try_index_event(event)
        return event

    def create_events(self, list_of_event_data: list[dict[str, Any]]) -> list[Event]:
        events = [Event(**apply_memory_policy(event_data)) for event_data in list_of_event_data]
        with self._session_factory() as session:
            session.add_all([self._to_record(event) for event in events])
            session.commit()
        for event in events:
            self._try_index_event(event)
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
        return [event for event in events if not event.hidden_from_default]

    def count_events(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(EventRecord)) or 0)

    def count_by_source(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = session.execute(select(EventRecord.source, func.count()).group_by(EventRecord.source)).all()
        return {str(source): int(count) for source, count in rows}

    def count_by_embedding_status(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = session.execute(select(EventRecord.embedding_status, func.count()).group_by(EventRecord.embedding_status)).all()
        return {str(status): int(count) for status, count in rows}

    def update_embedding_status(self, event_id: str, status: str) -> None:
        with self._session_factory() as session:
            record = session.get(EventRecord, event_id)
            if record is None:
                return
            record.embedding_status = status
            session.commit()

    def list_events_for_embedding(self, limit: int | None = None) -> list[Event]:
        with self._session_factory() as session:
            statement = select(EventRecord).order_by(EventRecord.created_at.asc())
            if limit is not None:
                statement = statement.limit(limit)
            records = session.scalars(statement).all()
            return [self._to_event(record) for record in records]

    def update_event_policy(self, event_id: str, policy: dict) -> None:
        with self._session_factory() as session:
            record = session.get(EventRecord, event_id)
            if record is None:
                return
            record.memory_category = str(policy["memory_category"])
            record.hidden_from_default = bool(policy["hidden_from_default"])
            record.is_indexable = bool(policy["is_indexable"])
            record.is_relationship_eligible = bool(policy["is_relationship_eligible"])
            record.is_context_eligible = bool(policy["is_context_eligible"])
            if not record.is_indexable:
                record.embedding_status = EmbeddingStatus.not_required.value
            session.commit()

    def count_policy_eligibility(self) -> dict[str, int]:
        events = self.list_all_events(include_hidden=True)
        return {
            "total_events": len(events),
            "indexable_events": sum(1 for event in events if event.is_indexable),
            "non_indexable_events": sum(1 for event in events if not event.is_indexable),
            "relationship_eligible_events": sum(1 for event in events if event.is_relationship_eligible),
            "context_eligible_events": sum(1 for event in events if event.is_context_eligible),
            "hidden_events": sum(1 for event in events if event.hidden_from_default),
        }

    def clear_events(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(EventRecord))
            session.commit()

    def delete_events_by_source(self, source: str) -> int:
        with self._session_factory() as session:
            result = session.execute(delete(EventRecord).where(EventRecord.source == source))
            session.commit()
            return int(result.rowcount or 0)

    def delete_events_by_ids(self, event_ids: list[str]) -> int:
        if not event_ids:
            return 0
        with self._session_factory() as session:
            result = session.execute(delete(EventRecord).where(EventRecord.id.in_(event_ids)))
            session.commit()
            return int(result.rowcount or 0)

    def _try_index_event(self, event: Event) -> None:
        try:
            from app.services.embedding_index_service import embedding_index_service

            embedding_index_service.index_event(event)
        except Exception:
            pass

    def _to_record(self, event: Event) -> EventRecord:
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
            memory_category=event.memory_category,
            hidden_from_default=event.hidden_from_default,
            is_indexable=event.is_indexable,
            is_relationship_eligible=event.is_relationship_eligible,
            is_context_eligible=event.is_context_eligible,
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
            memory_category=record.memory_category,
            hidden_from_default=bool(record.hidden_from_default),
            is_indexable=bool(record.is_indexable),
            is_relationship_eligible=bool(record.is_relationship_eligible),
            is_context_eligible=bool(record.is_context_eligible),
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
        event_category = event.memory_category
        if category and event_category != category:
            return False
        if event.hidden_from_default and not include_hidden:
            return category == "chat"
        return True
