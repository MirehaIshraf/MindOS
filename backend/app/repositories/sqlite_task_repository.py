from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.core.database import TaskRecord, get_session_factory, initialize_database
from app.domain.enums import TaskStatus, TaskType
from app.domain.models import TaskLog
from app.repositories.base import TaskRepository
from app.repositories.sqlite_utils import dumps_json, loads_json


class SQLiteTaskRepository(TaskRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

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
        with self._session_factory() as session:
            session.add(self._to_record(task))
            session.commit()
        return task

    def update_task_log(
        self,
        task_id: str,
        status: str | None = None,
        result: dict | None = None,
        confirmation_token: str | None = None,
        completed_at: datetime | None = None,
    ) -> TaskLog:
        with self._session_factory() as session:
            record = session.get(TaskRecord, task_id)
            if record is None:
                raise KeyError(task_id)
            if status:
                record.status = status
            if result is not None:
                record.result_json = dumps_json(result)
            if confirmation_token is not None:
                record.confirmation_token = None if confirmation_token == "" else confirmation_token
            if completed_at is not None:
                record.completed_at = completed_at
            session.commit()
            return self._to_task(record)

    def get_task_by_id(self, task_id: str) -> TaskLog | None:
        with self._session_factory() as session:
            record = session.get(TaskRecord, task_id)
            return self._to_task(record) if record else None

    def list_recent_tasks(self, limit: int = 20) -> list[TaskLog]:
        with self._session_factory() as session:
            records = session.scalars(select(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(limit)).all()
            return [self._to_task(record) for record in records]

    def list_pending_tasks(self) -> list[TaskLog]:
        with self._session_factory() as session:
            records = session.scalars(
                select(TaskRecord)
                .where(TaskRecord.status == TaskStatus.confirmation_required.value)
                .order_by(TaskRecord.created_at.desc())
            ).all()
            return [self._to_task(record) for record in records]

    def cancel_task(self, task_id: str) -> TaskLog:
        return self.update_task_log(
            task_id,
            status=TaskStatus.cancelled.value,
            confirmation_token="",
            completed_at=datetime.now(timezone.utc),
        )

    def find_by_confirmation_token(self, token: str) -> TaskLog | None:
        with self._session_factory() as session:
            record = session.scalar(select(TaskRecord).where(TaskRecord.confirmation_token == token))
            return self._to_task(record) if record else None

    def clear_tasks(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(TaskRecord))
            session.commit()

    def count_tasks(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(TaskRecord)) or 0)

    def _to_record(self, task: TaskLog) -> TaskRecord:
        return TaskRecord(
            id=task.id,
            task_type=task.task_type.value,
            instruction=task.instruction,
            status=task.status.value,
            preview_json=dumps_json(task.preview) if task.preview is not None else None,
            result_json=dumps_json(task.result) if task.result is not None else None,
            confirmation_token=task.confirmation_token,
            created_at=task.created_at,
            completed_at=task.completed_at,
        )

    def _to_task(self, record: TaskRecord) -> TaskLog:
        return TaskLog(
            id=record.id,
            task_type=TaskType(record.task_type),
            instruction=record.instruction,
            status=TaskStatus(record.status),
            preview=loads_json(record.preview_json, None),
            result=loads_json(record.result_json, None),
            confirmation_token=record.confirmation_token,
            created_at=record.created_at,
            completed_at=record.completed_at,
        )
