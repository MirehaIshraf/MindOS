from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskExecuteRequest(BaseModel):
    instruction: str
    dry_run: bool = True

    @field_validator("instruction")
    @classmethod
    def instruction_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("instruction must not be empty")
        return value


class TaskConfirmRequest(BaseModel):
    confirmation_token: str


class TaskCancelRequest(BaseModel):
    task_id: str


class TaskPreview(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    recipient: str | None = None
    subject: str | None = None
    body: str | None = None
    repo: str | None = None
    branch_name: str | None = None
    commit_message: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    report_markdown: str | None = None
    context_summary: str | None = None


class TaskResponse(BaseModel):
    task_id: str | None
    status: str
    task_type: str
    instruction: str
    preview: TaskPreview | dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    confirmation_token: str | None = None
    message: str
    sources_used: list[dict[str, Any]] = Field(default_factory=list)


class TaskHistoryItem(BaseModel):
    id: str
    task_type: str
    instruction: str
    status: str
    preview: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    confirmation_token: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class TaskHistoryResponse(BaseModel):
    tasks: list[TaskHistoryItem]
    total: int
