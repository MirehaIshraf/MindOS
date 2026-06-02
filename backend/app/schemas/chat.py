from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    use_context: bool = True
    session_id: str | None = None
    model_id: str | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value


class ChatRunCreateRequest(BaseModel):
    session_id: str | None = None
    message: str
    model_id: str | None = None
    use_memory: bool = True

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value


class ChatRunStartResponse(BaseModel):
    run_id: str
    session_id: str
    status: str
    message: str


class ChatRunStatusResponse(BaseModel):
    run_id: str
    session_id: str
    status: str
    user_message: str
    assistant_message: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    model_id: str | None = None
    provider: str | None = None
    answer_style: str | None = None
    intent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    current_step: str | None = None
    progress_message: str | None = None
    progress_percent: int | None = None
    progress_events: list[dict[str, Any]] = Field(default_factory=list)


class ActiveChatRunResponse(BaseModel):
    active_run: ChatRunStatusResponse | None = None


class ChatRunCancelResponse(BaseModel):
    run_id: str
    status: str
    message: str


class ChatSource(BaseModel):
    event_id: str
    source: str
    type: str
    title: str
    content_preview: str
    score: float
    match_reason: str
    timestamp: datetime
    source_kind: str = "direct"
    relationship_type: str | None = None
    relationship_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    url: str | None = None
    path: str | None = None


class ChatContextStats(BaseModel):
    direct_count: int
    related_count: int
    relationship_count: int
    sources: list[str]
    token_estimate: int
    warnings: list[str] = Field(default_factory=list)
    intent: str | None = None
    retrieval_profile: str | None = None
    search_terms: list[str] = Field(default_factory=list)
    preferred_sources: list[str] = Field(default_factory=list)
    excluded_types: list[str] = Field(default_factory=list)
    is_follow_up: bool = False
    resolved_query: str | None = None
    primary_source_event_id: str | None = None
    primary_source_title: str | None = None
    primary_source_url: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    sources_used: list[ChatSource]
    model: str
    provider: str = "fake"
    model_display_name: str = "FakeLLM"
    search_mode: str
    task_hint: str | None = None
    warning: str | None = None
    context_summary: str = ""
    context_stats: ChatContextStats | None = None
    answer_style: str = "normal"
    intent: str | None = None
    is_follow_up: bool = False
    resolved_query: str | None = None


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionsResponse(BaseModel):
    sessions: list[ChatSessionResponse]
    total: int


class ChatStoredMessageResponse(BaseModel):
    id: str
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
    created_at: datetime


class ChatResolveContextRequest(BaseModel):
    session_id: str
    query: str


class ChatResolveContextResponse(BaseModel):
    is_follow_up: bool
    resolved_query: str
    primary_source_event_id: str | None = None
    primary_source_title: str | None = None
    primary_source_url: str | None = None
    source_event_ids: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    reason: str = ""


class ChatMessagesResponse(BaseModel):
    messages: list[ChatStoredMessageResponse]
    total: int
