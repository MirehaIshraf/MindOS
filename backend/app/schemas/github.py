from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GitHubConfigRequest(BaseModel):
    token: str | None = None
    api_base_url: str = "https://api.github.com"

    @field_validator("api_base_url")
    @classmethod
    def api_base_url_must_not_be_empty(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            raise ValueError("api_base_url must not be empty")
        return cleaned


class GitHubStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    connected: bool
    status: str
    username: str | None = None
    api_base_url: str = "https://api.github.com"
    last_sync_at: str | None = None
    last_error: str | None = None
    repo_count: int = 0
    event_count: int = 0
    selected_repos: list[str] = Field(default_factory=list)
    selected_repositories: list[str] = Field(default_factory=list)
    sync_settings: dict[str, Any] = Field(default_factory=dict)


class GitHubTestResponse(BaseModel):
    status: str
    connected: bool
    username: str | None = None
    message: str


class GitHubRepo(BaseModel):
    full_name: str
    name: str
    owner: str
    private: bool = False
    html_url: str | None = None
    updated_at: datetime | None = None
    description: str | None = None


class GitHubReposResponse(BaseModel):
    repos: list[GitHubRepo]
    total: int


class GitHubSelectionRequest(BaseModel):
    repo_full_names: list[str] = Field(default_factory=list)
    sync_settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("repo_full_names")
    @classmethod
    def repo_names_must_be_reasonable(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) > 5:
            raise ValueError("Select up to 5 repositories.")
        return cleaned


class GitHubSyncRequest(BaseModel):
    repo_full_names: list[str] = Field(default_factory=list)
    include_commits: bool = True
    include_issues: bool = True
    include_pull_requests: bool = True
    max_items_per_type: int = Field(default=30, ge=1, le=100)

    @field_validator("repo_full_names")
    @classmethod
    def repo_names_must_not_be_empty(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("Select at least one repository.")
        if len(cleaned) > 5:
            raise ValueError("Sync at most 5 repositories at a time.")
        return cleaned


class GitHubSyncResponse(BaseModel):
    status: str
    repos_synced: int
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    events_created: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
