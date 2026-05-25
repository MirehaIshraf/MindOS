from app.domain.models import Relationship
from app.repositories.base import EventRepository, RelationshipRepository
from app.repositories.memory_event_repository import get_memory_event_repository


class MemoryRelationshipRepository(RelationshipRepository):
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._relationships: dict[str, Relationship] = {}
        self._event_repository = event_repository or get_memory_event_repository()

    def create_relationship(self, from_event_id: str, to_event_id: str, relationship_type: str, strength: float, reason: str) -> Relationship:
        if self.relationship_exists(from_event_id, to_event_id, relationship_type):
            for relationship in self._relationships.values():
                if (
                    relationship.from_event_id == from_event_id
                    and relationship.to_event_id == to_event_id
                    and relationship.relationship_type == relationship_type
                ):
                    return relationship
        relationship = Relationship(
            from_event_id=from_event_id,
            to_event_id=to_event_id,
            relationship_type=relationship_type,
            strength=strength,
            reason=reason,
        )
        self._relationships[relationship.id] = relationship
        return relationship

    def list_relationships_for_event(self, event_id: str, limit: int = 10) -> list[Relationship]:
        relationships = [
            relationship
            for relationship in self._relationships.values()
            if relationship.from_event_id == event_id or relationship.to_event_id == event_id
        ]
        relationships.sort(key=lambda item: item.strength, reverse=True)
        return relationships[:limit]

    def get_related_events(self, event_id: str, limit: int = 10) -> list[dict]:
        related = []
        for relationship in self.list_relationships_for_event(event_id, limit=limit):
            related_id = relationship.to_event_id if relationship.from_event_id == event_id else relationship.from_event_id
            event = self._event_repository.get_event_by_id(related_id)
            if event:
                related.append({"event": event, "relationship": relationship})
        return related

    def relationship_exists(self, from_event_id: str, to_event_id: str, relationship_type: str) -> bool:
        return any(
            relationship.from_event_id == from_event_id
            and relationship.to_event_id == to_event_id
            and relationship.relationship_type == relationship_type
            for relationship in self._relationships.values()
        )

    def clear_relationships(self) -> None:
        self._relationships.clear()

    def delete_relationships_for_event_ids(self, event_ids: list[str]) -> int:
        ids = set(event_ids)
        relationship_ids = [
            relationship_id
            for relationship_id, relationship in self._relationships.items()
            if relationship.from_event_id in ids or relationship.to_event_id in ids
        ]
        for relationship_id in relationship_ids:
            del self._relationships[relationship_id]
        return len(relationship_ids)

    def count_relationships(self) -> int:
        return len(self._relationships)

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for relationship in self._relationships.values():
            counts[relationship.relationship_type] = counts.get(relationship.relationship_type, 0) + 1
        return counts


memory_relationship_repository = MemoryRelationshipRepository()


def get_memory_relationship_repository() -> MemoryRelationshipRepository:
    return memory_relationship_repository
