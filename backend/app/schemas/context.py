from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ContextBuildRequest(BaseModel):
    query: str
    mode: str = "chat"
    limit: int = 5
    related_per_event: int = 2

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value

    @field_validator("limit")
    @classmethod
    def limit_in_range(cls, value: int) -> int:
        return max(1, min(value, 50))

    @field_validator("related_per_event")
    @classmethod
    def related_limit_in_range(cls, value: int) -> int:
        return max(0, min(value, 10))


class ContextEvent(BaseModel):
    event_id: str
    source: str
    type: str
    title: str
    content_preview: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
    score: float | None = None
    match_reason: str | None = None
    memory_category: str
    hidden_from_default: bool


class ContextRelationship(BaseModel):
    from_event_id: str
    to_event_id: str
    relationship_type: str
    strength: float
    reason: str


class ContextSourceGroup(BaseModel):
    source: str
    count: int
    event_ids: list[str]


class ContextPackage(BaseModel):
    query: str
    direct_events: list[ContextEvent] = Field(default_factory=list)
    related_events: list[ContextEvent] = Field(default_factory=list)
    relationships: list[ContextRelationship] = Field(default_factory=list)
    source_groups: list[ContextSourceGroup] = Field(default_factory=list)
    summary: str
    token_estimate: int
    warnings: list[str] = Field(default_factory=list)
