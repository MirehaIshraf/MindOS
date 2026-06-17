from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


DEFAULT_JIRA_ISSUE_TYPE = "Task"


class JiraConfigRequest(BaseModel):
    site_url: str
    email: str
    api_token: str
    default_project_key: str | None = None
    default_issue_type: str = DEFAULT_JIRA_ISSUE_TYPE

    @field_validator("site_url")
    @classmethod
    def site_url_must_be_jira_cloud(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme != "https":
            raise ValueError("Jira site URL must start with https://.")
        hostname = (parsed.hostname or "").lower()
        if not hostname.endswith(".atlassian.net"):
            raise ValueError("Jira site URL should look like https://your-company.atlassian.net.")
        return cleaned

    @field_validator("email")
    @classmethod
    def email_must_be_present(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "@" not in cleaned:
            raise ValueError("Atlassian email is required.")
        return cleaned

    @field_validator("api_token")
    @classmethod
    def token_must_be_present(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Jira API token is required.")
        return cleaned

    @field_validator("default_project_key")
    @classmethod
    def normalize_project_key(cls, value: str | None) -> str | None:
        cleaned = (value or "").strip().upper()
        return cleaned or None

    @field_validator("default_issue_type")
    @classmethod
    def issue_type_must_be_present(cls, value: str) -> str:
        cleaned = value.strip() or DEFAULT_JIRA_ISSUE_TYPE
        return cleaned


class JiraProject(BaseModel):
    id: str
    key: str
    name: str
    project_type_key: str | None = None
    simplified: bool | None = None
    style: str | None = None


class JiraStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    connected: bool
    status: str
    site_url: str | None = None
    email: str | None = None
    has_api_token: bool = False
    default_project_key: str | None = None
    default_issue_type: str = DEFAULT_JIRA_ISSUE_TYPE
    last_tested_at: str | None = None
    last_error: str | None = None
    display_name: str | None = None
    account_id: str | None = None
    project_count: int = 0


class JiraTestResponse(BaseModel):
    ok: bool
    connected: bool
    display_name: str | None = None
    account_id: str | None = None
    project_count: int = 0
    projects: list[JiraProject] = Field(default_factory=list)
    message: str


class JiraProjectsResponse(BaseModel):
    projects: list[JiraProject]
    total: int


class JiraConnectionResponse(BaseModel):
    status: str
    connected: bool
    message: str
    connector: JiraStatusResponse
