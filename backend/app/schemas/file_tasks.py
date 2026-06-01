from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AllowedFileOperation = Literal["create_folder", "move_file", "copy_file", "rename_file"]


class FileTaskPrepareRequest(BaseModel):
    root_path: str
    instruction: str
    max_depth: int = 2
    max_files: int = 500
    dry_run: bool = True

    @field_validator("root_path", "instruction")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class FileTaskScanRequest(BaseModel):
    root_path: str
    max_depth: int = 2
    max_files: int = 500


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
    warnings: list[str] = Field(default_factory=list)


class FileOperation(BaseModel):
    type: AllowedFileOperation
    from_path: str | None = None
    to_path: str | None = None
    path: str | None = None
    reason: str = ""


class SkippedFileItem(BaseModel):
    path: str
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
    skipped: list[SkippedFileItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    status: Literal["draft", "awaiting_confirmation", "blocked", "completed", "failed", "partial", "undone"] = "draft"
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
