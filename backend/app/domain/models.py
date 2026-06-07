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


class FileTaskLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    root_path: str
    instruction: str
    status: str
    plan: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] | None = None
    undo: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    executed_at: datetime | None = None
    undone_at: datetime | None = None


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
    intent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ChatRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    status: str = "queued"
    user_message: str
    resolved_query: str | None = None
    model_id: str | None = None
    provider: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    error: str | None = None
    result_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    current_step: str | None = None
    progress_message: str | None = None
    progress_percent: int | None = None
    progress_events: list[dict[str, Any]] = Field(default_factory=list)


class Relationship(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    from_event_id: str
    to_event_id: str
    relationship_type: str
    strength: float = 0.5
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


class SkillStep(BaseModel):
    step_index: int
    # Semantic action type — set by the LLM organiser
    action: str = "click"  # click | type | hotkey | navigate_url | open_app | key | scroll | focus | close_window | switch_window
    description: str = ""  # LLM-generated human-readable description
    app_name: str = ""
    window_title: str = ""
    element_type: str = ""
    element_name: str = ""
    # Action-specific payload fields
    text: str = ""           # text to type (type / navigate_url)
    url: str = ""            # destination URL (navigate_url)
    keys: list[str] = Field(default_factory=list)   # hotkey combo e.g. ["ctrl","t"]
    value: str = ""          # legacy key name field
    coordinates: dict[str, int] = Field(default_factory=dict)
    screenshot_b64: str = ""  # context screenshot (may be empty)
    is_destructive: bool = False
    requires_confirmation: bool = False


class Playbook(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str
    steps: list[SkillStep] = Field(default_factory=list)
    run_count: int = 0
    last_run_at: datetime | None = None
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
