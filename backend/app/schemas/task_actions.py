from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


ActionType = Literal[
    "multi_step",
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
    "document.summaryFromSearch",
    "document.reportFromSearch",
    "log.analyzeFromSearch",
    "unsupported",
]
TaskPlanStepType = Literal[
    "file.search_connected_folders",
    "file.select_candidates",
    "document.summarize_selected_files",
    "document.create_report_from_files",
    "document.create_output_file",
    "log.search_connected_logs",
    "log.analyze_selected_files",
    "gmail.create_draft",
    "gmail.send_email_after_confirmation",
    "gmail.attach_selected_files",
    "task.ask_user_to_choose_files",
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


class TaskIntentPlanStep(BaseModel):
    id: str
    type: TaskPlanStepType
    query: str | None = None
    purpose: str | None = None
    requires_user_selection: bool = False
    requires_confirmation: bool = False
    to: list[str] = Field(default_factory=list)
    subject_hint: str | None = None
    body_hint: str | None = None
    attachments_from_step: str | None = None
    files_from_step: str | None = None
    extensions: list[str] = Field(default_factory=list)
    latest_preference: bool = False
    exact_file_hint: str | None = None
    output_format: str | None = None
    filename_hint: str | None = None


class TaskIntentEntities(BaseModel):
    recipients: list[str] = Field(default_factory=list)
    file_queries: list[str] = Field(default_factory=list)
    topic_queries: list[str] = Field(default_factory=list)
    explicit_file_names: list[str] = Field(default_factory=list)
    action_words: list[str] = Field(default_factory=list)
    connector_words: list[str] = Field(default_factory=list)
    attachment_words: list[str] = Field(default_factory=list)
    output_words: list[str] = Field(default_factory=list)
    risk_words: list[str] = Field(default_factory=list)
    date_range: str | None = None
    output_format: str | None = None
    extensions: list[str] = Field(default_factory=list)
    latest_preference: bool = False
    exact_file_hint: str | None = None
    possible_intents: list[str] = Field(default_factory=list)


class TaskIntentPrepareRequest(BaseModel):
    instruction: str
    model_id: str | None = None
    use_llm_planner: bool = True

    @field_validator("instruction")
    @classmethod
    def instruction_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("instruction is required")
        return cleaned


class TaskIntentPrepareResponse(BaseModel):
    intent: Literal["multi_step", "single_step", "unsupported"]
    primary_action: str
    risk_level: RiskLevel
    requires_user_selection: bool = False
    requires_confirmation: bool = True
    confidence: float = 0.0
    source_type: str = "none"
    needs_file_search: bool = False
    needs_user_file_selection: bool = False
    needs_output_file: bool = False
    entities: TaskIntentEntities = Field(default_factory=TaskIntentEntities)
    steps: list[TaskIntentPlanStep] = Field(default_factory=list)
    explanation: str = ""
    user_facing_summary: str = ""
    planner_method: Literal["llm", "deterministic", "fallback"] = "deterministic"
    warnings: list[str] = Field(default_factory=list)
    validation_repairs: list[str] = Field(default_factory=list)


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
