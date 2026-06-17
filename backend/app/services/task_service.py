from datetime import datetime, timezone
from uuid import uuid4

from app.core.dependencies import get_event_repository, get_file_task_repository, get_task_repository
from app.domain.enums import EmbeddingStatus, EventSource, TaskStatus, TaskType
from app.integrations.tools.mock_email_tool import MockEmailTool
from app.integrations.tools.mock_github_tool import MockGitHubTool
from app.integrations.tools.mock_jira_tool import MockJiraTool
from app.repositories.base import EventRepository, FileTaskRepository, TaskRepository
from app.schemas.tasks import (
    TaskCancelRequest,
    TaskConfirmRequest,
    TaskExecuteRequest,
    TaskHistoryItem,
    TaskHistoryResponse,
    TaskPlan,
    TaskPlanningRequest,
    TaskPlanningResponse,
    TaskPreview,
    TaskResponse,
)
from app.services.relationship_service import relationship_service
from app.services.task_planner_service import task_planner_service


class TaskService:
    def __init__(
        self,
        task_repository: TaskRepository | None = None,
        event_repository: EventRepository | None = None,
        file_task_repository: FileTaskRepository | None = None,
    ) -> None:
        self._task_repository = task_repository or get_task_repository()
        self._event_repository = event_repository or get_event_repository()
        self._file_task_repository = file_task_repository or get_file_task_repository()
        self._pending_confirmations: dict[str, dict] = {}
        self._email_tool = MockEmailTool()
        self._jira_tool = MockJiraTool()
        self._github_tool = MockGitHubTool()

    def placeholder(self) -> dict[str, str]:
        return {
            "message": "Tasks module is ready. Use POST /tasks/execute.",
        }

    def execute_task(self, request: TaskExecuteRequest) -> TaskResponse:
        planning = task_planner_service.plan_task(
            TaskPlanningRequest(
                instruction=request.instruction,
                model_id=request.model_id,
                use_context=request.use_context,
            )
        )
        task_type = TaskType(planning.plan.task_type)
        sources = planning.plan.evidence
        preview = plan_to_preview(planning.plan, planning.context_summary, planning)

        if task_type == TaskType.unknown:
            task = self._task_repository.create_task_log(
                task_type=task_type.value,
                instruction=request.instruction,
                status=TaskStatus.failed.value,
                preview=preview.model_dump(exclude_none=True),
                result={"error": "unclassified"},
            )
            self._record_task_memory_event(
                event_type="task_failed",
                title="Failed task classification",
                content="MindOS could not classify the task instruction.",
                task_id=task.id,
                task_type=task_type,
                status=TaskStatus.failed,
                preview=preview,
                result=task.result,
            )
            return self._response(task.id, TaskStatus.failed, task_type, request.instruction, preview, task.result, None, "I could not classify this task yet.", sources, planning)

        if task_type in {TaskType.suggest_branch_name, TaskType.generate_commit_message, TaskType.weekly_report}:
            result = self._complete_read_only_task(task_type, preview)
            task = self._task_repository.create_task_log(
                task_type=task_type.value,
                instruction=request.instruction,
                status=TaskStatus.completed.value,
                preview=preview.model_dump(exclude_none=True),
                result=result,
            )
            task = self._task_repository.update_task_log(task.id, status=TaskStatus.completed.value, result=result, completed_at=datetime.now(timezone.utc))
            self._record_completed_task_event(task.id, task_type, request.instruction, preview, result, planning)
            return self._response(task.id, TaskStatus.completed, task_type, request.instruction, preview, result, None, "Task completed with a mock-safe preview.", sources, planning)

        token = str(uuid4())
        task = self._task_repository.create_task_log(
            task_type=task_type.value,
            instruction=request.instruction,
            status=TaskStatus.confirmation_required.value,
            preview=preview.model_dump(exclude_none=True),
            confirmation_token=token,
        )
        self._pending_confirmations[token] = {
            "token": token,
            "task_id": task.id,
            "task_type": task_type,
            "instruction": request.instruction,
            "preview": preview,
            "sources_used": sources,
            "planner_model": planning.model,
            "planner_provider": planning.provider,
            "planner_warning": planning.warning,
            "context_stats": planning.context_stats,
            "created_at": datetime.now(timezone.utc),
        }
        self._record_task_memory_event(
            event_type="task_prepared",
            title=f"Prepared {task_type.value} task",
            content=f"MindOS prepared a {task_type.value} task and is waiting for user confirmation.",
            task_id=task.id,
            task_type=task_type,
            status=TaskStatus.confirmation_required,
            preview=preview,
            result=None,
            extra_metadata={
                "confirmation_required": True,
                "mock": True,
                "planner_model": planning.model,
                "planner_provider": planning.provider,
                "evidence_count": len(planning.plan.evidence),
                "safety_notes": planning.plan.safety_notes,
            },
        )
        return self._response(
            task.id,
            TaskStatus.confirmation_required,
            task_type,
            request.instruction,
            preview,
            None,
            token,
            "Review this mock task preview before confirming.",
            sources,
            planning,
        )

    def confirm_task(self, request: TaskConfirmRequest) -> TaskResponse:
        pending = self._pending_confirmations.get(request.confirmation_token)
        task = self._task_repository.find_by_confirmation_token(request.confirmation_token)
        if pending is None and task is not None:
            restored_preview = TaskPreview(**(task.preview or {}))
            pending = {
                "token": request.confirmation_token,
                "task_id": task.id,
                "task_type": task.task_type,
                "instruction": task.instruction,
                "preview": restored_preview,
                "sources_used": restored_preview.evidence,
                "created_at": task.created_at,
                "planner_model": (task.preview or {}).get("planner_model"),
                "planner_provider": (task.preview or {}).get("planner_provider"),
                "planner_warning": (task.preview or {}).get("planner_warning"),
                "context_stats": (task.preview or {}).get("context_stats"),
            }

        if pending is None or task is None:
            event = self._event_repository.create_event(
                {
                    "source": EventSource.mindos,
                    "type": "task_failed",
                    "title": "Failed task confirmation",
                    "content": "MindOS could not confirm the task because the confirmation token was missing or expired.",
                    "metadata": {
                        "confirmation_token": request.confirmation_token,
                        "status": TaskStatus.failed.value,
                        "memory_category": "task",
                        "hidden_from_default": False,
                    },
                    "timestamp": datetime.now(timezone.utc),
                    "embedding_status": EmbeddingStatus.not_required,
                }
            )
            relationship_service.detect_relationships_for_event(event)
            return TaskResponse(
                task_id=None,
                status=TaskStatus.failed.value,
                task_type=TaskType.unknown.value,
                instruction="",
                preview=None,
                result={"error": "confirmation_not_found"},
                confirmation_token=None,
                message="Confirmation token was not found or already used.",
                sources_used=[],
                planner_model=None,
                planner_provider=None,
                planner_warning=None,
                context_stats=None,
            )

        task_type: TaskType = pending["task_type"]
        if task.status != TaskStatus.confirmation_required:
            return TaskResponse(
                task_id=task.id,
                status=task.status.value,
                task_type=task.task_type.value,
                instruction=task.instruction,
                preview=task.preview,
                result=task.result,
                confirmation_token=None,
                message="This task is no longer waiting for confirmation.",
                sources_used=[],
                planner_model=(task.preview or {}).get("planner_model"),
                planner_provider=(task.preview or {}).get("planner_provider"),
                planner_warning=(task.preview or {}).get("planner_warning"),
                context_stats=(task.preview or {}).get("context_stats"),
            )

        preview: TaskPreview = pending["preview"]
        result = self._execute_mock_tool(task_type, preview)
        task = self._task_repository.update_task_log(
            pending["task_id"],
            status=TaskStatus.completed.value,
            result=result,
            confirmation_token="",
            completed_at=datetime.now(timezone.utc),
        )
        self._pending_confirmations.pop(request.confirmation_token, None)
        self._record_task_memory_event(
            event_type="task_completed",
            title=f"Completed mock {task_type.value} task",
            content=f"User confirmed the task. MindOS completed a mock {task_type.value} action. No real external API was called.",
            task_id=task.id,
            task_type=task_type,
            status=TaskStatus.completed,
            preview=preview,
            result=result,
            extra_metadata={"mock": True},
        )
        planning = planning_from_preview(preview)
        return self._response(
            task.id,
            TaskStatus.completed,
            task_type,
            pending["instruction"],
            preview,
            result,
            None,
            "Mock task completed. No real external action was performed.",
            pending["sources_used"],
            planning,
        )

    def cancel_task(self, request: TaskCancelRequest) -> TaskResponse:
        task = self._task_repository.get_task_by_id(request.task_id)
        if task is None:
            raise KeyError("Task not found.")
        if task.status != TaskStatus.confirmation_required:
            raise ValueError("Task is not waiting for confirmation.")

        token = task.confirmation_token
        cancelled = self._task_repository.cancel_task(task.id)
        if token:
            self._pending_confirmations.pop(token, None)

        preview = TaskPreview(**(cancelled.preview or {}))
        self._record_task_memory_event(
            event_type="task_cancelled",
            title=f"Cancelled {cancelled.task_type.value} task",
            content=f"User cancelled a pending {cancelled.task_type.value} task before confirmation.",
            task_id=cancelled.id,
            task_type=cancelled.task_type,
            status=TaskStatus.cancelled,
            preview=preview,
            result=cancelled.result,
            extra_metadata={"mock": True},
        )
        planning = planning_from_preview(preview)
        return self._response(
            cancelled.id,
            TaskStatus.cancelled,
            cancelled.task_type,
            cancelled.instruction,
            preview,
            cancelled.result,
            None,
            "Task cancelled. No mock action was executed.",
            [],
            planning,
        )

    def plan_task(self, request: TaskPlanningRequest) -> TaskPlanningResponse:
        return task_planner_service.plan_task(request)

    def list_history(self, limit: int = 20) -> TaskHistoryResponse:
        tasks = self._task_repository.list_recent_tasks(limit=max(1, min(limit, 100)))
        return self._to_history_response(tasks)

    def list_pending(self) -> TaskHistoryResponse:
        return self._to_history_response(self._task_repository.list_pending_tasks())

    def _to_history_response(self, tasks) -> TaskHistoryResponse:
        items = []
        for task in tasks:
            preview = task.preview or ({} if task.status == TaskStatus.confirmation_required else None)
            preview_data = preview if isinstance(preview, dict) else {}
            sources_used = normalize_sources(preview_data.get("evidence", []))
            items.append(
                TaskHistoryItem(
                    id=task.id,
                    task_type=task.task_type.value,
                    instruction=task.instruction,
                    status=task.status.value,
                    preview=preview,
                    result=task.result,
                    confirmation_token=task.confirmation_token if task.status == TaskStatus.confirmation_required else None,
                    created_at=task.created_at,
                    completed_at=task.completed_at,
                    planner_model=preview_data.get("planner_model"),
                    planner_provider=preview_data.get("planner_provider"),
                    planner_warning=preview_data.get("planner_warning"),
                    context_stats=preview_data.get("context_stats"),
                    sources_used=sources_used,
                )
            )
        return TaskHistoryResponse(tasks=items, total=len(items))

    def clear_tasks(self) -> int:
        deleted_count = self.count_tasks()
        self._pending_confirmations.clear()
        self._task_repository.clear_tasks()
        self._file_task_repository.clear()
        return deleted_count

    def count_tasks(self) -> int:
        return self._task_repository.count_tasks() + self._file_task_repository.count()

    def _complete_read_only_task(self, task_type: TaskType, preview: TaskPreview) -> dict:
        if task_type == TaskType.suggest_branch_name:
            return {"mock": True, "branch_name": preview.branch_name}
        if task_type == TaskType.generate_commit_message:
            return {"mock": True, "commit_message": preview.commit_message}
        if task_type == TaskType.weekly_report:
            return {"mock": True, "report_markdown": preview.report_markdown}
        return {"mock": True}

    def _execute_mock_tool(self, task_type: TaskType, preview: TaskPreview) -> dict:
        params = preview.model_dump(exclude_none=True)
        if task_type == TaskType.create_jira_ticket:
            return self._jira_tool.execute(params=params)
        if task_type == TaskType.draft_email:
            return self._email_tool.execute(params=params)
        if task_type == TaskType.create_pull_request:
            return self._github_tool.execute(params=params)
        return {"mock": True, "status": "completed"}

    def _record_completed_task_event(
        self,
        task_id: str,
        task_type: TaskType,
        instruction: str,
        preview: TaskPreview,
        result: dict,
        planning: TaskPlanningResponse | None = None,
    ) -> None:
        if task_type == TaskType.suggest_branch_name:
            title = "Suggested branch name for JWT fix" if result.get("branch_name") == "fix/jwt-login-expiry" else "Suggested branch name"
            content = f"MindOS generated a branch name suggestion: {result.get('branch_name', '')}"
        elif task_type == TaskType.generate_commit_message:
            title = "Generated commit message"
            content = f"MindOS generated a commit message: {result.get('commit_message', '')}"
        elif task_type == TaskType.weekly_report:
            title = "Generated weekly report"
            content = "MindOS generated a weekly work report from local memory."
        else:
            title = f"Completed mock {task_type.value} task"
            content = f"MindOS completed a mock {task_type.value} task."

        self._record_task_memory_event(
            event_type="report_generated" if task_type == TaskType.weekly_report else "task_completed",
            title=title,
            content=content,
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.completed,
            preview=preview,
            result=result,
            extra_metadata={
                "instruction": instruction,
                "mock": True,
                "planner_model": planning.model if planning else None,
                "planner_provider": planning.provider if planning else None,
                "evidence_count": len(preview.evidence),
                "safety_notes": preview.safety_notes,
            },
        )

    def _record_task_memory_event(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        task_id: str,
        task_type: TaskType,
        status: TaskStatus,
        preview: TaskPreview | None,
        result: dict | None,
        extra_metadata: dict | None = None,
    ) -> None:
        metadata = {
            "task_id": task_id,
            "task_type": task_type.value,
            "status": status.value,
            "preview": preview.model_dump(exclude_none=True) if preview else None,
            "result": result,
            "mock": True,
            "memory_category": "report" if event_type == "report_generated" else "task",
            "hidden_from_default": False,
            "planner_model": preview.model_dump().get("planner_model") if preview else None,
            "planner_provider": preview.model_dump().get("planner_provider") if preview else None,
            "evidence_count": len(preview.evidence) if preview else 0,
            "safety_notes": preview.safety_notes if preview else [],
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        event = self._event_repository.create_event(
            {
                "source": EventSource.mindos,
                "type": event_type,
                "title": title,
                "content": content,
                "metadata": metadata,
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        relationship_service.detect_relationships_for_event(event)

    def _response(
        self,
        task_id: str | None,
        status: TaskStatus,
        task_type: TaskType,
        instruction: str,
        preview: TaskPreview | None,
        result: dict | None,
        token: str | None,
        message: str,
        sources: list[dict],
        planning: TaskPlanningResponse | None = None,
    ) -> TaskResponse:
        return TaskResponse(
            task_id=task_id,
            status=status.value,
            task_type=task_type.value,
            instruction=instruction,
            preview=preview,
            result=result,
            confirmation_token=token,
            message=message,
            sources_used=sources,
            planner_model=planning.model if planning else None,
            planner_provider=planning.provider if planning else None,
            planner_warning=planning.warning if planning else None,
            context_stats=planning.context_stats if planning else None,
        )


def plan_to_preview(plan: TaskPlan, context_summary: str | None, planning: TaskPlanningResponse | None = None) -> TaskPreview:
    return TaskPreview(
        title=plan.title,
        description=plan.description,
        priority=plan.priority,
        recipient=plan.recipient,
        subject=plan.subject,
        body=plan.body,
        repo=plan.repo,
        branch_name=plan.branch_name,
        commit_message=plan.commit_message,
        pr_title=plan.pr_title,
        pr_body=plan.pr_body,
        report_markdown=plan.report_markdown,
        context_summary=context_summary,
        confidence=plan.confidence,
        evidence=plan.evidence,
        missing_fields=plan.missing_fields,
        safety_notes=plan.safety_notes,
        planner_model=planning.model if planning else None,
        planner_provider=planning.provider if planning else None,
        planner_warning=planning.warning if planning else None,
        context_stats=planning.context_stats if planning else None,
    )


def planning_from_preview(preview: TaskPreview) -> TaskPlanningResponse:
    return TaskPlanningResponse(
        plan=TaskPlan(
            task_type=TaskType.unknown.value,
            confidence=preview.confidence or 0,
            evidence=preview.evidence,
            missing_fields=preview.missing_fields,
            safety_notes=preview.safety_notes,
        ),
        model=preview.planner_model or "unknown",
        provider=preview.planner_provider or "unknown",
        warning=preview.planner_warning,
        context_summary=preview.context_summary,
        context_stats=preview.context_stats,
    )


def normalize_sources(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    sources = []
    for item in value:
        if isinstance(item, dict):
            sources.append(item)
        elif item is not None:
            sources.append({"source": "memory", "title": str(item), "reason": ""})
    return sources


task_service = TaskService()
