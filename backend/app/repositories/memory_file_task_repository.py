from datetime import datetime, timezone

from app.domain.models import FileTaskLog
from app.repositories.base import FileTaskRepository


class MemoryFileTaskRepository(FileTaskRepository):
    def __init__(self) -> None:
        self._tasks: dict[str, FileTaskLog] = {}

    def create(self, data: dict) -> FileTaskLog:
        task = FileTaskLog(**data)
        self._tasks[task.id] = task
        return task

    def update(self, task_id: str, updates: dict) -> FileTaskLog:
        task = self._tasks[task_id]
        updated = task.model_copy(update={**updates, "updated_at": datetime.now(timezone.utc)})
        self._tasks[task_id] = updated
        return updated

    def get(self, task_id: str) -> FileTaskLog | None:
        return self._tasks.get(task_id)

    def list_recent(self, limit: int = 20) -> list[FileTaskLog]:
        return sorted(self._tasks.values(), key=lambda task: task.created_at, reverse=True)[:limit]

    def clear(self) -> None:
        self._tasks.clear()

    def count(self) -> int:
        return len(self._tasks)


memory_file_task_repository = MemoryFileTaskRepository()


def get_memory_file_task_repository() -> MemoryFileTaskRepository:
    return memory_file_task_repository
