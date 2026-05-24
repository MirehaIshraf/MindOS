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


class RecentEventsResponse(BaseModel):
    events: list[EventResponse]
    total: int
