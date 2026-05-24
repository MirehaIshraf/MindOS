from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import EventSource


class IngestEventRequest(BaseModel):
    source: EventSource
    type: str
    title: str
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class IngestEventResponse(BaseModel):
    event_id: str
    status: str = "ingested"


class BulkIngestResponse(BaseModel):
    ingested: int
    failed: int
    event_ids: list[str] = Field(default_factory=list)
