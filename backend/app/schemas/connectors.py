from typing import Any

from pydantic import BaseModel, Field, field_validator


class ConnectorStatus(BaseModel):
    name: str
    display_name: str | None = None
    description: str | None = None
    status: str
    enabled: bool = False
    events_count: int | None = None
    last_event_at: str | None = None
    supports_manual_import: bool | None = None
    supports_live_watch: bool | None = None


class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorStatus]


class FilePreviewRequest(BaseModel):
    folder_path: str
    recursive: bool = True
    max_files: int = Field(default=50, ge=1, le=1000)
    max_file_size_kb: int = Field(default=256, ge=1, le=2048)
    allowed_extensions: list[str] | None = None

    @field_validator("folder_path")
    @classmethod
    def folder_path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("folder_path must not be empty")
        return value


class FileImportRequest(BaseModel):
    folder_path: str
    recursive: bool = True
    max_files: int = Field(default=100, ge=1, le=1000)
    max_file_size_kb: int = Field(default=256, ge=1, le=2048)
    allowed_extensions: list[str] | None = None

    @field_validator("folder_path")
    @classmethod
    def folder_path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("folder_path must not be empty")
        return value


class FilePreviewResult(BaseModel):
    total_candidates: int
    preview_files: list[dict[str, Any]]
    skipped: list[dict[str, Any]]


class FileImportResult(BaseModel):
    imported_count: int
    skipped_count: int
    failed_count: int
    events_created: list[str]
    skipped: list[dict[str, Any]]
    failed: list[dict[str, Any]]
    message: str


class LogPreviewRequest(BaseModel):
    file_path: str
    max_lines: int = Field(default=200, ge=1, le=10000)
    only_errors: bool = False

    @field_validator("file_path")
    @classmethod
    def file_path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("file_path must not be empty")
        return value


class LogImportRequest(BaseModel):
    file_path: str
    max_lines: int = Field(default=1000, ge=1, le=10000)
    only_errors: bool = False
    group_similar: bool = True

    @field_validator("file_path")
    @classmethod
    def file_path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("file_path must not be empty")
        return value


class LogLinePreview(BaseModel):
    line_number: int
    level: str
    message: str
    timestamp: str | None = None
    raw: str


class LogPreviewResult(BaseModel):
    file_path: str
    total_lines_scanned: int
    matched_lines: int
    preview: list[LogLinePreview]
    skipped: list[dict[str, Any]]
    message: str


class LogImportResult(BaseModel):
    imported_count: int
    skipped_count: int
    failed_count: int
    events_created: list[str]
    groups_created: int
    message: str


class GitPreviewRequest(BaseModel):
    repo_path: str
    max_commits: int = Field(default=10, ge=1, le=500)

    @field_validator("repo_path")
    @classmethod
    def repo_path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("repo_path must not be empty")
        return value


class GitImportRequest(BaseModel):
    repo_path: str
    max_commits: int = Field(default=50, ge=1, le=500)
    include_diff_summary: bool = True
    include_status: bool = True

    @field_validator("repo_path")
    @classmethod
    def repo_path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("repo_path must not be empty")
        return value


class GitCommitPreview(BaseModel):
    hash: str
    short_hash: str
    author: str
    date: str
    message: str


class GitPreviewResult(BaseModel):
    repo_path: str
    repo_name: str
    current_branch: str | None = None
    is_git_repo: bool
    recent_commits: list[GitCommitPreview]
    status_summary: dict[str, Any]
    message: str


class GitImportResult(BaseModel):
    imported_count: int
    skipped_count: int
    failed_count: int
    events_created: list[str]
    message: str
