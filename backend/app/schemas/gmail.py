from pydantic import BaseModel, Field, field_validator


REQUIRED_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailCredentialsUploadRequest(BaseModel):
    filename: str = "credentials.json"
    content: str

    @field_validator("filename")
    @classmethod
    def filename_must_be_json(cls, value: str) -> str:
        cleaned = value.strip() or "credentials.json"
        if not cleaned.lower().endswith(".json"):
            raise ValueError("Upload a Google OAuth credentials.json file.")
        return cleaned


class GmailStatusResponse(BaseModel):
    credentials_configured: bool
    connected: bool
    reconnect_required: bool = False
    status: str
    email_address: str | None = None
    scopes: list[str] = Field(default_factory=list)
    last_error: str | None = None
    connected_at: str | None = None
    credential_file_name: str | None = None
    required_scopes: list[str] = Field(default_factory=lambda: list(REQUIRED_GMAIL_SCOPES))
    capabilities: dict[str, bool | int] = Field(default_factory=dict)


class GmailConnectResponse(BaseModel):
    status: str
    auth_url: str
    message: str


class GmailTestResponse(BaseModel):
    status: str
    connected: bool
    email_address: str | None = None
    message: str


class GmailDraftRequest(BaseModel):
    to: str
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str

    @field_validator("to", "subject", "body")
    @classmethod
    def required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned


class GmailDraftResponse(BaseModel):
    status: str
    draft_id: str
    message_id: str | None = None
    message: str


class GmailSendRequest(BaseModel):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    confirmation: bool = False

    @field_validator("to")
    @classmethod
    def recipients_required(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("Add a recipient before sending.")
        return cleaned

    @field_validator("subject", "body")
    @classmethod
    def send_text_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned


class GmailSendResponse(BaseModel):
    status: str
    message_id: str | None = None
    thread_id: str | None = None
    message: str


class GmailDraftPrepareSourceItem(BaseModel):
    type: str = "task"
    title: str
    summary: str = ""
    status: str | None = None
    created_at: str | None = None
    context_name: str | None = None
    output_file_name: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class GmailDraftPrepareRequest(BaseModel):
    instruction: str
    connected_email: str | None = None
    recent_tasks: list[GmailDraftPrepareSourceItem] = Field(default_factory=list)
    memory_items: list[GmailDraftPrepareSourceItem] = Field(default_factory=list)
    model_id: str | None = None


class GmailDraftPrepareResponse(BaseModel):
    to: str = ""
    subject: str
    body: str
    tone: str = "professional"
    source_summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    model_display_name: str | None = None
    planner_warning: str | None = None


class GmailSendDraftResponse(BaseModel):
    status: str
    draft_id: str
    message_id: str | None = None
    message: str


class GmailRecentEmail(BaseModel):
    id: str
    thread_id: str | None = None
    subject: str = ""
    from_address: str = ""
    date: str | None = None
    snippet: str = ""


class GmailRecentEmailsResponse(BaseModel):
    emails: list[GmailRecentEmail]
    total: int
