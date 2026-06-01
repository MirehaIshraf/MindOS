from datetime import datetime, timezone

from app.adapters.file_adapter import FileAdapter, file_adapter
from app.core.dependencies import get_event_repository, get_file_task_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.domain.models import FileTaskLog
from app.repositories.base import EventRepository, FileTaskRepository
from app.schemas.file_tasks import (
    FileOperation,
    FileSnapshotResponse,
    FileTaskExecuteRequest,
    FileTaskExecutionResult,
    FileTaskPlan,
    FileTaskPrepareRequest,
    FileTaskRecentResponse,
    FileTaskRecordResponse,
    FileTaskScanRequest,
    FileTaskUndoResult,
    SkippedFileItem,
    UndoOperation,
)
from app.services.file_snapshot_service import file_snapshot_service
from app.services.file_task_planner_service import file_task_planner_service
from app.services.file_task_safety_service import file_task_safety_service


class FileTaskExecutionService:
    def __init__(
        self,
        repository: FileTaskRepository | None = None,
        events: EventRepository | None = None,
        adapter: FileAdapter | None = None,
    ) -> None:
        self._repository = repository or get_file_task_repository()
        self._events = events or get_event_repository()
        self._adapter = adapter or file_adapter

    def scan(self, request: FileTaskScanRequest) -> FileSnapshotResponse:
        root, blocked = file_task_safety_service.validate_root(request.root_path)
        if blocked:
            raise ValueError("; ".join(blocked))
        return file_snapshot_service.scan(str(root), request.max_depth, request.max_files)

    def prepare(self, request: FileTaskPrepareRequest) -> FileTaskPlan:
        snapshot = self.scan(FileTaskScanRequest(root_path=request.root_path, max_depth=request.max_depth, max_files=request.max_files))
        plan = file_task_planner_service.plan(root_path=snapshot.root_path, instruction=request.instruction, snapshot=snapshot)
        validation = file_task_safety_service.validate_plan(plan.root_path, plan.operations)
        blocked = [*plan.blocked_reasons, *validation["blocked_reasons"]]
        warnings = [*snapshot.warnings, *plan.warnings, *validation["warnings"]]
        status = "blocked" if blocked or not plan.operations else "awaiting_confirmation"
        plan = plan.model_copy(
            update={
                "blocked_reasons": dedupe(blocked),
                "warnings": dedupe(warnings),
                "status": status,
                "requires_confirmation": True,
            }
        )
        self._repository.create(
            {
                "id": plan.task_id,
                "root_path": plan.root_path,
                "instruction": plan.instruction,
                "status": plan.status,
                "plan": plan.model_dump(mode="json"),
                "validation": validation,
                "execution": None,
                "undo": [],
            }
        )
        self._record_memory_event(
            event_type="file_task_prepared",
            title="Prepared file organization task",
            content=f"{plan.summary}\nOperations planned: {len(plan.operations)}\nStatus: {plan.status}",
            metadata={
                "task_id": plan.task_id,
                "root_path": plan.root_path,
                "operation_count": len(plan.operations),
                "risk_level": plan.risk_level,
                "status": plan.status,
            },
            indexable=False,
        )
        return plan

    def execute(self, task_id: str, request: FileTaskExecuteRequest) -> FileTaskExecutionResult:
        if not request.confirmation:
            raise ValueError("Confirmation is required.")
        task = self._require_task(task_id)
        plan = FileTaskPlan(**task.plan)
        validation = file_task_safety_service.validate_plan(plan.root_path, plan.operations)
        if validation["blocked_reasons"]:
            result = FileTaskExecutionResult(task_id=task_id, status="failed", errors=validation["blocked_reasons"], undo_available=False)
            self._repository.update(task_id, {"status": "failed", "execution": result.model_dump(mode="json"), "validation": validation, "executed_at": datetime.now(timezone.utc)})
            self._record_file_task_failed(task_id, plan, result)
            return result

        counts = {"created_folders": 0, "moved_files": 0, "copied_files": 0, "renamed_files": 0}
        errors: list[str] = []
        skipped: list[SkippedFileItem] = []
        undo: list[UndoOperation] = []
        for operation in plan.operations:
            try:
                self._execute_operation(operation, counts, undo)
            except Exception as error:
                errors.append(f"{operation.type}: {error}")
        status = "completed" if not errors else "partial" if any(counts.values()) else "failed"
        result = FileTaskExecutionResult(task_id=task_id, status=status, skipped=skipped, errors=errors, undo_available=bool(undo), **counts)
        self._repository.update(
            task_id,
            {
                "status": status,
                "execution": result.model_dump(mode="json"),
                "undo": [item.model_dump(mode="json") for item in undo],
                "executed_at": datetime.now(timezone.utc),
            },
        )
        if status == "failed":
            self._record_file_task_failed(task_id, plan, result)
        else:
            self._record_file_task_completed(task_id, plan, result)
        return result

    def undo(self, task_id: str) -> FileTaskUndoResult:
        task = self._require_task(task_id)
        operations = [UndoOperation(**item) for item in task.undo]
        if not operations:
            raise ValueError("No undo plan is available.")
        errors: list[str] = []
        undone = 0
        for operation in reversed(operations):
            try:
                if operation.type == "move_file" and operation.from_path and operation.to_path:
                    self._adapter.move_file(operation.from_path, operation.to_path)
                elif operation.type == "rename_file" and operation.from_path and operation.to_path:
                    self._adapter.rename_file(operation.from_path, operation.to_path)
                elif operation.type == "remove_created_folder_if_empty" and operation.path:
                    self._adapter.remove_folder_if_empty(operation.path)
                undone += 1
            except Exception as error:
                errors.append(f"{operation.type}: {error}")
        status = "undone" if not errors else "partial" if undone else "failed"
        result = FileTaskUndoResult(task_id=task_id, status=status, undone_operations=undone, errors=errors)
        self._repository.update(task_id, {"status": status, "undone_at": datetime.now(timezone.utc)})
        self._record_memory_event(
            event_type="file_task_undone",
            title="Undid file organization task",
            content=f"Undo status: {status}. Operations undone: {undone}.",
            metadata={"task_id": task_id, "status": status, "undone_operations": undone},
            indexable=True,
        )
        return result

    def get(self, task_id: str) -> FileTaskRecordResponse:
        return self._to_response(self._require_task(task_id))

    def recent(self, limit: int = 20) -> FileTaskRecentResponse:
        tasks = [self._to_response(task) for task in self._repository.list_recent(max(1, min(limit, 100)))]
        return FileTaskRecentResponse(tasks=tasks, total=len(tasks))

    def _execute_operation(self, operation: FileOperation, counts: dict[str, int], undo: list[UndoOperation]) -> None:
        if operation.type == "create_folder" and operation.path:
            result = self._adapter.create_folder(operation.path)
            if result["status"] == "created":
                counts["created_folders"] += 1
                undo.append(UndoOperation(type="remove_created_folder_if_empty", path=operation.path))
            return
        if operation.type == "move_file" and operation.from_path and operation.to_path:
            self._adapter.move_file(operation.from_path, operation.to_path)
            counts["moved_files"] += 1
            undo.append(UndoOperation(type="move_file", from_path=operation.to_path, to_path=operation.from_path))
            return
        if operation.type == "copy_file" and operation.from_path and operation.to_path:
            self._adapter.copy_file(operation.from_path, operation.to_path)
            counts["copied_files"] += 1
            return
        if operation.type == "rename_file" and operation.from_path and operation.to_path:
            self._adapter.rename_file(operation.from_path, operation.to_path)
            counts["renamed_files"] += 1
            undo.append(UndoOperation(type="rename_file", from_path=operation.to_path, to_path=operation.from_path))
            return
        raise ValueError(f"Invalid operation payload: {operation.type}")

    def _require_task(self, task_id: str) -> FileTaskLog:
        task = self._repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _to_response(self, task: FileTaskLog) -> FileTaskRecordResponse:
        return FileTaskRecordResponse(
            task_id=task.id,
            root_path=task.root_path,
            instruction=task.instruction,
            status=task.status,
            plan=FileTaskPlan(**task.plan),
            execution=FileTaskExecutionResult(**task.execution) if task.execution else None,
            undo=[UndoOperation(**item) for item in task.undo],
            created_at=task.created_at,
            updated_at=task.updated_at,
            executed_at=task.executed_at,
            undone_at=task.undone_at,
        )

    def _record_file_task_completed(self, task_id: str, plan: FileTaskPlan, result: FileTaskExecutionResult) -> None:
        self._record_memory_event(
            event_type="file_task_completed",
            title="Completed file organization task",
            content=(
                f"{plan.summary}\nCreated folders: {result.created_folders}\nMoved files: {result.moved_files}\n"
                f"Copied files: {result.copied_files}\nRenamed files: {result.renamed_files}"
            ),
            metadata={**result.model_dump(mode="json"), "task_id": task_id, "root_path": plan.root_path},
            indexable=True,
        )

    def _record_file_task_failed(self, task_id: str, plan: FileTaskPlan, result: FileTaskExecutionResult) -> None:
        self._record_memory_event(
            event_type="file_task_failed",
            title="Failed file organization task",
            content=f"{plan.summary}\nErrors: {'; '.join(result.errors)}",
            metadata={**result.model_dump(mode="json"), "task_id": task_id, "root_path": plan.root_path},
            indexable=True,
        )

    def _record_memory_event(self, *, event_type: str, title: str, content: str, metadata: dict, indexable: bool) -> None:
        self._events.create_event(
            {
                "source": EventSource.mindos,
                "type": event_type,
                "title": title,
                "content": content,
                "metadata": {**metadata, "memory_category": "task", "hidden_from_default": False},
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
                "is_indexable": indexable,
                "is_relationship_eligible": False,
                "is_context_eligible": indexable,
            }
        )


def dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


file_task_execution_service = FileTaskExecutionService()
