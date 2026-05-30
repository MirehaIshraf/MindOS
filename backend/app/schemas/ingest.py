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


class ExternalEventIngestRequest(BaseModel):
    source: str
    type: str
    title: str = ""
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None
    client_id: str | None = None
    session_id: str | None = None


class ExternalBulkIngestRequest(BaseModel):
    events: list[ExternalEventIngestRequest]


class ExternalIngestResponse(BaseModel):
    status: str
    event_id: str
    message: str


class ExternalBulkIngestResponse(BaseModel):
    status: str
    ingested: int
    failed: int
    event_ids: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class CollectorClientResponse(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool = True
    last_seen_at: datetime | None = None
    events_count: int = 0


class CollectorClientsResponse(BaseModel):
    collectors: list[CollectorClientResponse]


class ExternalIngestStatusResponse(BaseModel):
    external_ingest_enabled: bool
    supported_sources: list[str]
    preferred_event_types: dict[str, list[str]]
    recent_external_events: int
    collector_clients: list[CollectorClientResponse]
