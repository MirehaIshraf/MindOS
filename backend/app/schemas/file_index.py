from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


DEFAULT_FILE_INDEX_EXTENSIONS = [
    ".txt",
    ".md",
    ".log",
    ".json",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".pdf",
    ".docx",
    ".doc",
    ".py",
    ".java",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".sql",
]

DEFAULT_FILE_INDEX_EXCLUDE_PATTERNS = ["node_modules", ".git", "dist", "build", "__pycache__", "**/__pycache__/**"]


class FileIndexRunResult(BaseModel):
    source_id: str
    root_path: str
    file_count: int = 0
    inventory_count: int = 0
    indexed_count: int = 0
    content_failed_count: int = 0
    skipped_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    failed_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    failed: list[dict[str, Any]] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    message: str
    missing_count: int = 0


class TrackedFolderCreateRequest(BaseModel):
    path: str
    name: str | None = None
    enabled: bool = True
    indexing_enabled: bool = True
    recursive: bool = True
    max_depth: int = Field(default=5, ge=0, le=10)
    max_files: int = Field(default=2000, ge=1, le=5000)
    max_file_size_mb: int = Field(default=5, ge=1, le=25)
    include_hidden: bool = False
    allowed_extensions: list[str] = Field(default_factory=lambda: list(DEFAULT_FILE_INDEX_EXTENSIONS))
    exclude_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_FILE_INDEX_EXCLUDE_PATTERNS))
    index_interval_minutes: int = Field(default=20, ge=10, le=30)

    @field_validator("path")
    @classmethod
    def path_must_not_be_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("path must not be empty")
        return cleaned


class TrackedFolderUpdateRequest(BaseModel):
    path: str | None = None
    name: str | None = None
    enabled: bool | None = None
    indexing_enabled: bool | None = None
    recursive: bool | None = None
    max_depth: int | None = Field(default=None, ge=0, le=10)
    max_files: int | None = Field(default=None, ge=1, le=5000)
    max_file_size_mb: int | None = Field(default=None, ge=1, le=25)
    include_hidden: bool | None = None
    allowed_extensions: list[str] | None = None
    exclude_patterns: list[str] | None = None
    index_interval_minutes: int | None = Field(default=None, ge=10, le=30)


class TrackedFolderResponse(BaseModel):
    id: str
    name: str
    path: str
    enabled: bool
    indexing_enabled: bool
    index_status: str = "idle"
    last_indexed_at: str | None = None
    next_index_after: str | None = None
    last_error: str | None = None
    file_count: int = 0
    indexed_count: int = 0
    inventory_count: int = 0
    content_failed_count: int = 0
    skipped_count: int = 0
    missing_count: int = 0
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TrackedFoldersResponse(BaseModel):
    folders: list[TrackedFolderResponse]
    total: int


class FileIndexJobResponse(BaseModel):
    job_id: str
    source_id: str
    status: str
    reason: str
    message: str = ""
    queued_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class FileIndexJobsResponse(BaseModel):
    jobs: list[FileIndexJobResponse]
    total: int


class IndexedFileSearchRequest(BaseModel):
    query: str
    source_ids: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    search_content: bool = True
    search_filename: bool = True
    connected_sources_only: bool = True
    attachable_only: bool = False
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query must not be empty")
        return cleaned


class IndexedFileSearchMatch(BaseModel):
    event_id: str | None = None
    source_id: str
    file_name: str
    relative_path: str
    extension: str
    size_bytes: int
    modified_at: str | None = None
    score: float
    match_reason: str
    matched_excerpt: str = ""
    content_index_status: str = "unknown"
    attachable: bool = False


class IndexedFileSearchResponse(BaseModel):
    matches: list[IndexedFileSearchMatch]


class IndexedFileAttachmentReference(BaseModel):
    source_id: str
    relative_path: str

    @field_validator("source_id", "relative_path")
    @classmethod
    def value_must_not_be_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned


class ResolveIndexedAttachmentsRequest(BaseModel):
    files: list[IndexedFileAttachmentReference] = Field(default_factory=list)


class ResolvedIndexedAttachment(BaseModel):
    id: str
    file_name: str
    source_id: str
    relative_path: str
    size_bytes: int = 0
    extension: str = ""
    attachable: bool
    reason: str | None = None


class ResolveIndexedAttachmentsResponse(BaseModel):
    attachments: list[ResolvedIndexedAttachment]
