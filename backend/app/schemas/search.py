from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str
    sources: list[str] | None = None
    category: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    include_hidden: bool = True

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value


class SearchResult(BaseModel):
    event_id: str
    source: str
    type: str
    title: str
    content_preview: str
    metadata: dict[str, Any]
    timestamp: datetime
    created_at: datetime
    embedding_status: str
    memory_category: str
    hidden_from_default: bool
    score: float
    match_reason: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    search_mode: str
    warning: str | None = None


class SearchStatsResponse(BaseModel):
    total_events: int
    visible_default_events: int
    hidden_events: int
    by_source: dict[str, int]
    by_category: dict[str, int]
    last_ingested_at: datetime | None
