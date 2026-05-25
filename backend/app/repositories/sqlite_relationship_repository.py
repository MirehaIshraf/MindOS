from sqlalchemy import delete, func, or_, select

from app.core.database import RelationshipRecord, get_session_factory, initialize_database
from app.domain.models import Relationship
from app.repositories.base import EventRepository, RelationshipRepository
from app.repositories.sqlite_event_repository import SQLiteEventRepository


class SQLiteRelationshipRepository(RelationshipRepository):
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        initialize_database()
        self._session_factory = get_session_factory()
        self._event_repository = event_repository or SQLiteEventRepository()

    def create_relationship(self, from_event_id: str, to_event_id: str, relationship_type: str, strength: float, reason: str) -> Relationship:
        existing = self._find_record(from_event_id, to_event_id, relationship_type)
        if existing:
            return self._to_relationship(existing)
        relationship = Relationship(
            from_event_id=from_event_id,
            to_event_id=to_event_id,
            relationship_type=relationship_type,
            strength=strength,
            reason=reason,
        )
        with self._session_factory() as session:
            session.add(
                RelationshipRecord(
                    id=relationship.id,
                    from_event_id=relationship.from_event_id,
                    to_event_id=relationship.to_event_id,
                    relationship_type=relationship.relationship_type,
                    strength=relationship.strength,
                    reason=relationship.reason,
                    created_at=relationship.created_at,
                )
            )
            session.commit()
        return relationship

    def list_relationships_for_event(self, event_id: str, limit: int = 10) -> list[Relationship]:
        with self._session_factory() as session:
            records = session.scalars(
                select(RelationshipRecord)
                .where(or_(RelationshipRecord.from_event_id == event_id, RelationshipRecord.to_event_id == event_id))
                .order_by(RelationshipRecord.strength.desc())
                .limit(limit)
            ).all()
            return [self._to_relationship(record) for record in records]

    def get_related_events(self, event_id: str, limit: int = 10) -> list[dict]:
        related = []
        for relationship in self.list_relationships_for_event(event_id, limit=limit):
            related_id = relationship.to_event_id if relationship.from_event_id == event_id else relationship.from_event_id
            event = self._event_repository.get_event_by_id(related_id)
            if event:
                related.append({"event": event, "relationship": relationship})
        return related

    def relationship_exists(self, from_event_id: str, to_event_id: str, relationship_type: str) -> bool:
        return self._find_record(from_event_id, to_event_id, relationship_type) is not None

    def clear_relationships(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(RelationshipRecord))
            session.commit()

    def delete_relationships_for_event_ids(self, event_ids: list[str]) -> int:
        if not event_ids:
            return 0
        with self._session_factory() as session:
            result = session.execute(
                delete(RelationshipRecord).where(
                    or_(
                        RelationshipRecord.from_event_id.in_(event_ids),
                        RelationshipRecord.to_event_id.in_(event_ids),
                    )
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def count_relationships(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(RelationshipRecord)) or 0)

    def count_by_type(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = session.execute(select(RelationshipRecord.relationship_type, func.count()).group_by(RelationshipRecord.relationship_type)).all()
        return {str(kind): int(count) for kind, count in rows}

    def _find_record(self, from_event_id: str, to_event_id: str, relationship_type: str) -> RelationshipRecord | None:
        with self._session_factory() as session:
            return session.scalar(
                select(RelationshipRecord).where(
                    RelationshipRecord.from_event_id == from_event_id,
                    RelationshipRecord.to_event_id == to_event_id,
                    RelationshipRecord.relationship_type == relationship_type,
                )
            )

    def _to_relationship(self, record: RelationshipRecord) -> Relationship:
        return Relationship(
            id=record.id,
            from_event_id=record.from_event_id,
            to_event_id=record.to_event_id,
            relationship_type=record.relationship_type,
            strength=record.strength,
            reason=record.reason or "",
            created_at=record.created_at,
        )
