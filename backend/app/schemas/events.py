from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.domain.enums import EmbeddingStatus, EventSource


class EventResponse(BaseModel):
    id: str
    source: EventSource
    type: str
    title: str
    content: str
    metadata: dict[str, Any]
    timestamp: datetime
    created_at: datetime
    embedding_status: EmbeddingStatus
    memory_category: str
    hidden_from_default: bool
    related_count: int = 0


class RecentEventsResponse(BaseModel):
    events: list[EventResponse]
    total: int


class RelationshipResponse(BaseModel):
    id: str
    from_event_id: str
    to_event_id: str
    relationship_type: str
    strength: float
    reason: str
    created_at: datetime


class RelatedEventItem(BaseModel):
    event: EventResponse
    relationship: RelationshipResponse


class RelatedEventsResponse(BaseModel):
    event_id: str
    related: list[RelatedEventItem]
    total: int
