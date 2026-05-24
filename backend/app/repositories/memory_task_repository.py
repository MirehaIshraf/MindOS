from datetime import datetime, timezone

from app.domain.enums import TaskStatus, TaskType
from app.domain.models import TaskLog
from app.repositories.base import TaskRepository


class MemoryTaskRepository(TaskRepository):
    def __init__(self) -> None:
        self._tasks: dict[str, TaskLog] = {}

    def create_task_log(
        self,
        task_type: str,
        instruction: str,
        status: str,
        preview: dict | None = None,
        result: dict | None = None,
        confirmation_token: str | None = None,
    ) -> TaskLog:
        task = TaskLog(
            task_type=TaskType(task_type),
            instruction=instruction,
            status=TaskStatus(status),
            preview=preview,
            result=result,
            confirmation_token=confirmation_token,
        )
        self._tasks[task.id] = task
        return task

    def update_task_log(
        self,
        task_id: str,
        status: str | None = None,
        result: dict | None = None,
        confirmation_token: str | None = None,
        completed_at: datetime | None = None,
    ) -> TaskLog:
        task = self._tasks[task_id]
        update_data = {
            "status": TaskStatus(status) if status else task.status,
            "result": result if result is not None else task.result,
            "confirmation_token": None if confirmation_token == "" else confirmation_token if confirmation_token is not None else task.confirmation_token,
            "completed_at": completed_at if completed_at is not None else task.completed_at,
            "updated_at": datetime.now(timezone.utc),
        }
        updated = task.model_copy(update=update_data)
        self._tasks[task_id] = updated
        return updated

    def get_task_by_id(self, task_id: str) -> TaskLog | None:
        return self._tasks.get(task_id)

    def list_recent_tasks(self, limit: int = 20) -> list[TaskLog]:
        return sorted(self._tasks.values(), key=lambda task: task.created_at, reverse=True)[:limit]

    def list_pending_tasks(self) -> list[TaskLog]:
        tasks = [task for task in self._tasks.values() if task.status == TaskStatus.confirmation_required]
        return sorted(tasks, key=lambda task: task.created_at, reverse=True)

    def cancel_task(self, task_id: str) -> TaskLog:
        return self.update_task_log(
            task_id,
            status=TaskStatus.cancelled.value,
            confirmation_token="",
            completed_at=datetime.now(timezone.utc),
        )

    def find_by_confirmation_token(self, token: str) -> TaskLog | None:
        for task in self._tasks.values():
            if task.confirmation_token == token:
                return task
        return None

    def clear_tasks(self) -> None:
        self._tasks.clear()

    def count_tasks(self) -> int:
        return len(self._tasks)


memory_task_repository = MemoryTaskRepository()


def get_memory_task_repository() -> MemoryTaskRepository:
    return memory_task_repository
