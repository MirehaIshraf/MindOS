from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


ActionType = Literal[
    "gmail.createDraft",
    "gmail.searchEmails",
    "gmail.summarizeEmails",
    "gmail.sendEmail",
    "gmail.sendDraft",
    "gmail.replyDraft",
    "git.commit",
    "git.push",
    "github.createIssue",
    "github.createPullRequest",
    "file.organize",
    "document.summary",
    "unsupported",
]
RiskLevel = Literal["safe", "low", "medium", "high"]
ExecutionStatus = Literal["completed", "failed", "partial"]


class ActionCapability(BaseModel):
    available: bool
    provider: str
    risk_level: RiskLevel
    requires_confirmation: bool
    reason: str | None = None


class ActionCapabilityRegistry(BaseModel):
    capabilities: dict[str, ActionCapability]


class PreparedAction(BaseModel):
    id: str = Field(default_factory=lambda: f"action_{uuid4().hex}")
    action_type: ActionType
    title: str
    summary: str
    risk_level: RiskLevel
    requires_confirmation: bool = True
    can_execute: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    preview: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskActionExecuteRequest(BaseModel):
    action_id: str
    action_type: ActionType
    preview: dict[str, Any] = Field(default_factory=dict)
    confirmation: bool = False

    @field_validator("action_id")
    @classmethod
    def action_id_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("action_id is required")
        return cleaned


class TaskActionExecuteResponse(BaseModel):
    ok: bool
    status: ExecutionStatus
    result: dict[str, Any] = Field(default_factory=dict)
    message: str
