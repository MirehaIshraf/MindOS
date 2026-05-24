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

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value


class ChatSource(BaseModel):
    event_id: str
    source: str
    type: str
    title: str
    content_preview: str
    score: float
    match_reason: str
    timestamp: datetime


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    sources_used: list[ChatSource]
    model: str
    search_mode: str
    task_hint: str | None = None
    warning: str | None = None


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
    search_mode: str | None = None
    task_hint: str | None = None
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    messages: list[ChatStoredMessageResponse]
    total: int
