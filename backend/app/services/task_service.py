from datetime import datetime, timezone
from uuid import uuid4

from app.core.dependencies import get_event_repository, get_task_repository
from app.domain.enums import EmbeddingStatus, EventSource, TaskStatus, TaskType
from app.integrations.tools.mock_email_tool import MockEmailTool
from app.integrations.tools.mock_github_tool import MockGitHubTool
from app.integrations.tools.mock_jira_tool import MockJiraTool
from app.repositories.base import EventRepository, TaskRepository
from app.schemas.tasks import (
    TaskCancelRequest,
    TaskConfirmRequest,
    TaskExecuteRequest,
    TaskHistoryItem,
    TaskHistoryResponse,
    TaskPreview,
    TaskResponse,
)
from app.schemas.context import ContextEvent, ContextPackage
from app.services.context_builder_service import ContextBuilderService
from app.services.relationship_service import relationship_service


class TaskService:
    def __init__(
        self,
        task_repository: TaskRepository | None = None,
        event_repository: EventRepository | None = None,
        context_builder: ContextBuilderService | None = None,
    ) -> None:
        self._task_repository = task_repository or get_task_repository()
        self._event_repository = event_repository or get_event_repository()
        self._context_builder = context_builder or ContextBuilderService()
        self._pending_confirmations: dict[str, dict] = {}
        self._email_tool = MockEmailTool()
        self._jira_tool = MockJiraTool()
        self._github_tool = MockGitHubTool()

    def placeholder(self) -> dict[str, str]:
        return {
            "message": "Tasks module is ready. Use POST /tasks/execute.",
        }

    def execute_task(self, request: TaskExecuteRequest) -> TaskResponse:
        task_type = classify_task(request.instruction)
        context_package = self._context_builder.build_task_context(request.instruction, limit=5, related_per_event=2)
        sources = context_sources(context_package)
        preview = self._build_preview(task_type, request.instruction, context_package)

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
            return self._response(task.id, TaskStatus.failed, task_type, request.instruction, preview, task.result, None, "I could not classify this task yet.", sources)

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
            self._record_completed_task_event(task.id, task_type, request.instruction, preview, result)
            return self._response(task.id, TaskStatus.completed, task_type, request.instruction, preview, result, None, "Task completed with a mock-safe preview.", sources)

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
        )

    def confirm_task(self, request: TaskConfirmRequest) -> TaskResponse:
        pending = self._pending_confirmations.get(request.confirmation_token)
        task = self._task_repository.find_by_confirmation_token(request.confirmation_token)
        if pending is None and task is not None:
            pending = {
                "token": request.confirmation_token,
                "task_id": task.id,
                "task_type": task.task_type,
                "instruction": task.instruction,
                "preview": TaskPreview(**(task.preview or {})),
                "sources_used": [],
                "created_at": task.created_at,
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
        )

    def list_history(self, limit: int = 20) -> TaskHistoryResponse:
        tasks = self._task_repository.list_recent_tasks(limit=max(1, min(limit, 100)))
        return self._to_history_response(tasks)

    def list_pending(self) -> TaskHistoryResponse:
        return self._to_history_response(self._task_repository.list_pending_tasks())

    def _to_history_response(self, tasks) -> TaskHistoryResponse:
        items = [
            TaskHistoryItem(
                id=task.id,
                task_type=task.task_type.value,
                instruction=task.instruction,
                status=task.status.value,
                preview=task.preview,
                result=task.result,
                confirmation_token=task.confirmation_token if task.status == TaskStatus.confirmation_required else None,
                created_at=task.created_at,
                completed_at=task.completed_at,
            )
            for task in tasks
        ]
        return TaskHistoryResponse(tasks=items, total=len(items))

    def clear_tasks(self) -> None:
        self._pending_confirmations.clear()
        self._task_repository.clear_tasks()

    def count_tasks(self) -> int:
        return self._task_repository.count_tasks()

    def _build_preview(self, task_type: TaskType, instruction: str, context_package: ContextPackage) -> TaskPreview:
        summary = context_package.summary
        title = infer_title(instruction, context_package)
        branch_name = infer_branch_name(instruction, context_package)
        commit_message = infer_commit_message(instruction, context_package)

        if task_type == TaskType.suggest_branch_name:
            return TaskPreview(branch_name=branch_name, context_summary=summary)
        if task_type == TaskType.generate_commit_message:
            return TaskPreview(commit_message=commit_message, context_summary=summary)
        if task_type == TaskType.weekly_report:
            return TaskPreview(report_markdown=build_report(context_package), context_summary=summary)
        if task_type == TaskType.create_jira_ticket:
            return TaskPreview(title=title, description=build_description(instruction, summary), priority="medium", context_summary=summary)
        if task_type == TaskType.draft_email:
            return TaskPreview(recipient="", subject=title, body=build_description(instruction, summary), context_summary=summary)
        if task_type == TaskType.create_pull_request:
            return TaskPreview(repo="", pr_title=title, pr_body=build_description(instruction, summary), branch_name=branch_name, context_summary=summary)
        return TaskPreview(context_summary=summary)

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
        )


def classify_task(instruction: str) -> TaskType:
    text = instruction.lower().strip()
    if "branch name" in text or text.startswith("suggest branch"):
        return TaskType.suggest_branch_name
    if "commit message" in text or "generate commit" in text:
        return TaskType.generate_commit_message
    if ("jira" in text or "ticket" in text) and any(word in text for word in ["create", "draft", "make"]):
        return TaskType.create_jira_ticket
    if "email" in text and any(word in text for word in ["draft", "write", "send"]):
        return TaskType.draft_email
    if "pull request" in text or "pr" in text:
        return TaskType.create_pull_request
    if "weekly report" in text or "report" in text:
        return TaskType.weekly_report
    return TaskType.unknown


def context_sources(context_package: ContextPackage) -> list[dict]:
    sources = []
    for source_kind, events in [("direct", context_package.direct_events), ("related", context_package.related_events)]:
        for event in events:
            sources.append(
                {
                    "event_id": event.event_id,
                    "source": event.source,
                    "type": event.type,
                    "title": event.title,
                    "content_preview": event.content_preview,
                    "score": event.score,
                    "match_reason": event.match_reason,
                    "source_kind": source_kind,
                }
            )
    return sources


def context_events(context_package: ContextPackage) -> list[ContextEvent]:
    return [*context_package.direct_events, *context_package.related_events]


def infer_title(instruction: str, context_package: ContextPackage) -> str:
    events = context_events(context_package)
    if events:
        return events[0].title
    return instruction.strip().rstrip(".")[:80]


def infer_branch_name(instruction: str, context_package: ContextPackage) -> str:
    events = context_events(context_package)
    text = f"{instruction} {' '.join(event.title for event in events[:3])}".lower()
    if "jwt" in text or "login" in text or "auth" in text:
        return "fix/jwt-login-expiry"
    words = [word for word in text.replace("_", "-").split() if word.isalnum()][:4]
    return "work/" + "-".join(words or ["mindos-task"])


def infer_commit_message(instruction: str, context_package: ContextPackage) -> str:
    events = context_events(context_package)
    text = f"{instruction} {' '.join(event.title for event in events[:3])}".lower()
    if "jwt" in text or "auth" in text or "login" in text:
        return "fix(auth): handle expired JWT refresh flow"
    return "chore: update local work context"


def build_description(instruction: str, summary: str) -> str:
    return f"{instruction.strip()}\n\nContext:\n{summary}"


def build_report(context_package: ContextPackage) -> str:
    events = context_events(context_package)
    activity = "\n".join(f"- {event.title} ({event.source})" for event in events[:8]) or "- No matching activity found."
    sources = ", ".join(group.source for group in context_package.source_groups) or "none"
    return (
        "# Weekly Work Report\n\n"
        f"## Summary\n{context_package.summary}\n\n"
        f"## Sources\n{sources}\n\n"
        f"## Key Activity\n{activity}\n\n"
        "## Issues Found\n- Review related failures or warnings in local memory.\n\n"
        "## Suggested Next Actions\n- Confirm priorities and prepare follow-up tasks if needed."
    )


task_service = TaskService()
