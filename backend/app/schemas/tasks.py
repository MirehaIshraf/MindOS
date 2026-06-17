from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskExecuteRequest(BaseModel):
    instruction: str
    dry_run: bool = True
    model_id: str | None = None
    use_context: bool = True

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


class TaskPlan(BaseModel):
    task_type: str
    confidence: float = 0.0
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
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    planner_model: str | None = None
    planner_provider: str | None = None
    planner_warning: str | None = None
    context_stats: dict[str, Any] | None = None

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_plan_evidence(cls, value: Any) -> list[dict[str, Any]]:
        return normalize_evidence_items(value)


class TaskPlanningRequest(BaseModel):
    instruction: str
    task_type: str | None = None
    model_id: str | None = None
    use_context: bool = True

    @field_validator("instruction")
    @classmethod
    def planning_instruction_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("instruction must not be empty")
        return value


class TaskPlanningResponse(BaseModel):
    plan: TaskPlan
    model: str
    provider: str
    warning: str | None = None
    context_summary: str | None = None
    context_stats: dict[str, Any] | None = None


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
    confidence: float | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    planner_model: str | None = None
    planner_provider: str | None = None
    planner_warning: str | None = None
    context_stats: dict[str, Any] | None = None

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_preview_evidence(cls, value: Any) -> list[dict[str, Any]]:
        return normalize_evidence_items(value)


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
    planner_model: str | None = None
    planner_provider: str | None = None
    planner_warning: str | None = None
    context_stats: dict[str, Any] | None = None


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
    planner_model: str | None = None
    planner_provider: str | None = None
    planner_warning: str | None = None
    context_stats: dict[str, Any] | None = None
    sources_used: list[dict[str, Any]] = Field(default_factory=list)


class TaskHistoryResponse(BaseModel):
    tasks: list[TaskHistoryItem]
    total: int


class TaskHistoryClearResponse(BaseModel):
    ok: bool = True
    deleted_count: int


def normalize_evidence_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(item)
        elif item is not None:
            normalized.append({"source": "memory", "title": str(item), "reason": ""})
    return normalized
