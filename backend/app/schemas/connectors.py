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
