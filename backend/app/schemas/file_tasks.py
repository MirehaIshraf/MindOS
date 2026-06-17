from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AllowedFileOperation = Literal["create_folder", "move_file", "copy_file", "rename_file"]


class FileTaskPrepareRequest(BaseModel):
    root_path: str
    instruction: str
    max_depth: int = Field(default=2, ge=0, le=5)
    max_files: int = Field(default=500, ge=1, le=1000)
    include_hidden: bool = False
    mode: str = "organize"
    dry_run: bool = True

    @field_validator("root_path", "instruction")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class FileTaskScanRequest(BaseModel):
    root_path: str
    max_depth: int = Field(default=2, ge=0, le=5)
    max_files: int = Field(default=500, ge=1, le=1000)
    include_hidden: bool = False

    @field_validator("root_path")
    @classmethod
    def root_path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Folder path is required.")
        return value


class FileSnapshotItem(BaseModel):
    name: str
    path: str
    relative_path: str
    extension: str
    size_bytes: int
    modified_at: datetime
    is_dir: bool
    is_hidden: bool


class FileSnapshotResponse(BaseModel):
    root_path: str
    files: list[FileSnapshotItem] = Field(default_factory=list)
    folders: list[FileSnapshotItem] = Field(default_factory=list)
    total_files: int
    total_folders: int
    total_size_bytes: int = 0
    max_depth: int = 2
    max_files: int = 500
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)


class BrowserFilePlanSnapshotItem(BaseModel):
    name: str
    relative_path: str
    extension: str = ""
    size_bytes: int = 0
    modified_at: str | None = None
    category: str | None = None
    is_hidden: bool = False


class BrowserFolderItem(BaseModel):
    name: str
    relative_path: str
    is_hidden: bool = False


class FileTaskLlmPlanRequest(BaseModel):
    instruction: str
    root_name: str
    files: list[BrowserFilePlanSnapshotItem] = Field(default_factory=list)
    folders: list[BrowserFolderItem] = Field(default_factory=list)
    allowed_operations: list[str] = Field(default_factory=lambda: ["create_folder", "move_file"])
    max_operations: int = Field(default=500, ge=1, le=500)
    model_id: str | None = None

    @field_validator("instruction", "root_name")
    @classmethod
    def llm_plan_values_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class DocumentSummaryInputFile(BaseModel):
    relative_path: str
    extension: str = ""
    text: str


class DocumentSummarySkippedFile(BaseModel):
    relative_path: str
    reason: str


class DocumentSummaryPrepareRequest(BaseModel):
    instruction: str
    folder_name: str
    files: list[DocumentSummaryInputFile] = Field(default_factory=list)
    files_skipped: list[DocumentSummarySkippedFile] = Field(default_factory=list)
    output_format: Literal["markdown", "text"] = "markdown"
    output_filename: str | None = None
    summary_style: Literal["brief", "detailed", "file_by_file", "report"] = "detailed"
    model_id: str | None = None

    @field_validator("instruction", "folder_name")
    @classmethod
    def document_summary_values_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class DocumentSummaryPrepareResponse(BaseModel):
    task_id: str
    status: Literal["preview", "empty", "unsupported", "failed"]
    summary_title: str
    summary_markdown: str
    files_used: list[str] = Field(default_factory=list)
    files_skipped: list[DocumentSummarySkippedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    output_filename_suggestion: str = "mindos-summary.md"
    model: str | None = None
    provider: str | None = None
    model_display_name: str | None = None
    planner_warning: str | None = None
    output_format: Literal["markdown", "text"] = "markdown"
    summary_style: Literal["brief", "detailed", "file_by_file", "report"] = "detailed"
    topic: str | None = None
    naming_confidence: Literal["high", "medium", "low"] = "low"
    naming_method: Literal["llm", "deterministic", "fallback"] = "fallback"


class DocumentSummaryCompleteRequest(BaseModel):
    task_id: str
    folder_name: str
    output_file_name: str
    files_used_count: int = Field(default=0, ge=0)
    files_skipped_count: int = Field(default=0, ge=0)
    summary_style: Literal["brief", "detailed", "file_by_file", "report"] = "detailed"
    output_format: Literal["markdown", "text"] = "markdown"
    file_types_used: list[str] = Field(default_factory=list)
    summary_title: str | None = None
    topic: str | None = None
    naming_confidence: Literal["high", "medium", "low"] = "low"

    @field_validator("task_id", "folder_name", "output_file_name")
    @classmethod
    def document_summary_completion_values_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class DocumentSummaryCompleteResponse(BaseModel):
    status: Literal["recorded", "completed_with_warning"]
    task_type: str = "document_summary"
    memory_event_id: str | None = None
    warning: str | None = None


class IndexedDocumentSummaryFileReference(BaseModel):
    source_id: str
    relative_path: str

    @field_validator("source_id", "relative_path")
    @classmethod
    def indexed_file_reference_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class IndexedDocumentSummaryPrepareRequest(BaseModel):
    query: str
    style: Literal["brief", "detailed", "file_by_file", "report"] = "detailed"
    output_format: Literal["markdown", "text"] = "markdown"
    output_filename: str | None = None
    files: list[IndexedDocumentSummaryFileReference] = Field(default_factory=list)
    model_id: str | None = None

    @field_validator("query")
    @classmethod
    def indexed_summary_query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value.strip()


class GeneratedSummaryOutputFile(BaseModel):
    id: str
    file_name: str
    path: str
    size_bytes: int
    mime_type: str
    source_task_id: str | None = None
    source_step_id: str | None = None
    selected: bool = True


class GeneratedSummarySaveRequest(BaseModel):
    task_id: str
    output_filename: str
    content: str

    @field_validator("task_id", "output_filename", "content")
    @classmethod
    def generated_output_values_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class GeneratedSummarySaveResponse(BaseModel):
    ok: bool = True
    output_file: GeneratedSummaryOutputFile


class LogAnalysisFileReference(BaseModel):
    source_id: str
    relative_path: str

    @field_validator("source_id", "relative_path")
    @classmethod
    def log_file_reference_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class LogAnalysisPrepareRequest(BaseModel):
    query: str
    files: list[LogAnalysisFileReference] = Field(default_factory=list)
    output_format: Literal["markdown"] = "markdown"
    output_filename: str | None = None
    model_id: str | None = None

    @field_validator("query")
    @classmethod
    def log_analysis_query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value.strip()


class LogEvidenceFile(BaseModel):
    relative_path: str
    error_lines: list[str] = Field(default_factory=list)
    surrounding_context: list[str] = Field(default_factory=list)
    repeated_patterns: list[str] = Field(default_factory=list)
    last_lines: list[str] = Field(default_factory=list)
    chars_used: int = 0


class LogAnalysisPrepareResponse(BaseModel):
    task_id: str
    status: Literal["preview", "empty", "failed"]
    report_title: str
    report_markdown: str
    files_used: list[str] = Field(default_factory=list)
    files_skipped: list[DocumentSummarySkippedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    output_filename_suggestion: str = "log-error-analysis-report.md"
    evidence: list[LogEvidenceFile] = Field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    model_display_name: str | None = None
    planner_warning: str | None = None


class LogAnalysisSaveRequest(BaseModel):
    task_id: str
    output_filename: str
    report_markdown: str

    @field_validator("task_id", "output_filename", "report_markdown")
    @classmethod
    def log_analysis_save_values_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class FileOperation(BaseModel):
    id: str = ""
    type: AllowedFileOperation
    tool: str = ""
    from_path: str | None = None
    to_path: str | None = None
    path: str | None = None
    relative_from: str | None = None
    relative_to: str | None = None
    reason: str = ""
    status: Literal["planned", "blocked"] = "planned"


class SkippedFileItem(BaseModel):
    path: str
    relative_path: str | None = None
    reason: str


class FileTaskPlan(BaseModel):
    task_id: str
    task_type: str = "file_organize"
    root_path: str
    instruction: str
    summary: str
    risk_level: Literal["low", "medium", "high"] = "low"
    requires_confirmation: bool = True
    operations: list[FileOperation] = Field(default_factory=list)
    folders_to_create: list[FileOperation] = Field(default_factory=list)
    files_to_move: list[FileOperation] = Field(default_factory=list)
    skipped: list[SkippedFileItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    status: Literal["draft", "awaiting_confirmation", "blocked", "empty", "unsupported", "completed", "failed", "partial", "undone"] = "draft"
    total_operations: int = 0
    create_folder_count: int = 0
    move_file_count: int = 0
    copy_file_count: int = 0
    rename_file_count: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)
    preview_only: bool = True
    planner_model: str | None = None
    planner_provider: str | None = None
    planner_warning: str | None = None


class FileTaskExecuteRequest(BaseModel):
    confirmation: bool


class FileTaskExecutionResult(BaseModel):
    task_id: str
    status: Literal["completed", "failed", "partial", "cancelled"]
    created_folders: int = 0
    moved_files: int = 0
    copied_files: int = 0
    renamed_files: int = 0
    skipped: list[SkippedFileItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    undo_available: bool = False


class UndoOperation(BaseModel):
    type: Literal["move_file", "remove_created_folder_if_empty", "rename_file"]
    from_path: str | None = None
    to_path: str | None = None
    path: str | None = None
    reason: str = "Reverse operation"


class FileTaskUndoResult(BaseModel):
    task_id: str
    status: Literal["undone", "partial", "failed"]
    undone_operations: int = 0
    errors: list[str] = Field(default_factory=list)


class FileTaskRecordResponse(BaseModel):
    task_id: str
    root_path: str
    instruction: str
    status: str
    plan: FileTaskPlan
    execution: FileTaskExecutionResult | None = None
    undo: list[UndoOperation] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None = None
    undone_at: datetime | None = None


class FileTaskRecentResponse(BaseModel):
    tasks: list[FileTaskRecordResponse]
    total: int


def model_to_jsonable(value: BaseModel | dict[str, Any] | list[Any] | None) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
