from pydantic import BaseModel, Field, field_validator


class EmailConfigRequest(BaseModel):
    provider: str = "imap"
    email_address: str | None = None
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_ssl: bool = True
    username: str | None = None
    password: str | None = None
    sync_scope: str = "recent"
    folder_name: str = "INBOX"
    max_items: int = Field(default=25, ge=1, le=100)

    @field_validator("imap_port")
    @classmethod
    def port_in_range(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError("imap_port must be between 1 and 65535")
        return value

    @field_validator("sync_scope")
    @classmethod
    def scope_valid(cls, value: str) -> str:
        allowed = {"recent", "unread", "starred", "folder"}
        if value not in allowed:
            raise ValueError(f"sync_scope must be one of: {', '.join(sorted(allowed))}")
        return value


class EmailStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    connected: bool
    status: str
    provider: str = "imap"
    account_email: str | None = None
    last_sync_at: str | None = None
    last_error: str | None = None
    selected_scope: str = "recent"
    event_count: int = 0
    has_credentials: bool = False


class EmailTestResponse(BaseModel):
    status: str
    connected: bool
    account_email: str | None = None
    message: str


class EmailFolder(BaseModel):
    name: str
    display_name: str
    message_count: int = 0


class EmailFoldersResponse(BaseModel):
    folders: list[EmailFolder]
    total: int


class EmailAttachment(BaseModel):
    filename: str
    mime_type: str
    size: int = 0


class EmailSyncRequest(BaseModel):
    scope: str = "recent"
    folder_name: str = "INBOX"
    max_items: int = Field(default=25, ge=1, le=100)
    include_body_excerpt: bool = True

    @field_validator("scope")
    @classmethod
    def scope_valid(cls, value: str) -> str:
        allowed = {"recent", "unread", "starred", "folder"}
        if value not in allowed:
            raise ValueError(f"scope must be one of: {', '.join(sorted(allowed))}")
        return value


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
