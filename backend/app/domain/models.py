from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.enums import (
    EmbeddingStatus,
    EventSource,
    TaskStatus,
    TaskType,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: EventSource
    type: str
    title: str
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    embedding_status: EmbeddingStatus = EmbeddingStatus.not_required
    memory_category: str | None = None
    hidden_from_default: bool = False
    is_indexable: bool = True
    is_relationship_eligible: bool = True
    is_context_eligible: bool = True


class TaskLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_type: TaskType = TaskType.unknown
    status: TaskStatus = TaskStatus.pending
    instruction: str
    preview: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    confirmation_token: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChatStoredMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    role: str
    content: str
    sources_used: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    model_display_name: str | None = None
    search_mode: str | None = None
    task_hint: str | None = None
    context_summary: str | None = None
    context_stats: dict[str, Any] | None = None
    warning: str | None = None
    answer_style: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Relationship(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    from_event_id: str
    to_event_id: str
    relationship_type: str
    strength: float = 0.5
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


class Playbook(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str
    steps: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ConnectorSource(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    connector_type: str
    name: str
    path: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_import_at: datetime | None = None
    last_import_status: str | None = None
    last_import_message: str | None = None


class ImportRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str | None = None
    connector_type: str
    path: str
    status: str
    imported_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    message: str = ""
    result_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
