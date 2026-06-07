from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


EmailAuthType = Literal["bearer", "api_key_header", "none"]
EmailSyncScope = Literal["recent", "unread", "search"]


class EmailToolMapping(BaseModel):
    test: str = "email.test"
    search: str = "email.search"
    get: str = "email.get"
    list_folders: str = "email.list_folders"
    create_draft: str = "email.create_draft"


class EmailMcpConfigRequest(BaseModel):
    provider_type: str = "email_mcp"
    provider_name: str = "Custom Email MCP"
    api_base_url: str = "mock"
    auth_type: EmailAuthType = "none"
    auth_header_name: str = "Authorization"
    api_key: str | None = None
    account_label: str | None = None
    tool_mapping: EmailToolMapping = Field(default_factory=EmailToolMapping)

    @field_validator("provider_type")
    @classmethod
    def provider_type_must_be_email_mcp(cls, value: str) -> str:
        if value.strip() != "email_mcp":
            raise ValueError("provider_type must be email_mcp")
        return "email_mcp"

    @field_validator("provider_name", "api_base_url", "auth_header_name")
    @classmethod
    def required_text_must_not_be_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned


class EmailCapabilityResponse(BaseModel):
    search_emails: bool = False
    read_email: bool = False
    list_folders: bool = False
    create_draft: bool = False
    send_email: bool = False
    delete_email: bool = False
    modify_email: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class EmailStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    connected: bool
    status: str
    provider_type: str = "email_mcp"
    provider_name: str | None = None
    api_base_url: str | None = None
    auth_type: EmailAuthType = "none"
    auth_header_name: str = "Authorization"
    account_label: str | None = None
    last_sync_at: str | None = None
    last_error: str | None = None
    selected_scope: EmailSyncScope = "recent"
    event_count: int = 0
    has_api_key: bool = False
    capabilities: EmailCapabilityResponse = Field(default_factory=EmailCapabilityResponse)


class EmailTestResponse(BaseModel):
    status: str
    connected: bool
    provider_name: str | None = None
    account_label: str | None = None
    capabilities: EmailCapabilityResponse = Field(default_factory=EmailCapabilityResponse)
    message: str


class EmailConnectResponse(BaseModel):
    status: str
    connected: bool
    message: str


class EmailDisconnectResponse(BaseModel):
    status: str
    message: str


class EmailSyncRequest(BaseModel):
    scope: EmailSyncScope = "recent"
    query: str | None = None
    max_items: int = Field(default=25, ge=1, le=100)


class NormalizedEmailAttachment(BaseModel):
    filename: str = ""
    mime_type: str = ""
    size: int | None = None


class NormalizedEmailMessage(BaseModel):
    id: str
    thread_id: str | None = None
    subject: str = ""
    from_address: str = Field(default="", alias="from")
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    date: str | None = None
    snippet: str = ""
    body_excerpt: str = ""
    labels: list[str] = Field(default_factory=list)
    folder: str | None = None
    has_attachments: bool = False
    attachments: list[NormalizedEmailAttachment] = Field(default_factory=list)
    url: str | None = None

    model_config = {"populate_by_name": True}


class EmailSyncResponse(BaseModel):
    status: str
    emails_seen: int
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    events_created: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str


class EmailDraftRequest(BaseModel):
    to: str = ""
    subject: str
    body: str
    provider: str = "email_mcp"

    @field_validator("subject", "body")
    @classmethod
    def required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned


class EmailDraftResponse(BaseModel):
    ok: bool
    draft_id: str
    url: str | None = None
    message: str
