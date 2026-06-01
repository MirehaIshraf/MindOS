from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.core.database import FileTaskRecord, get_session_factory, initialize_database
from app.domain.models import FileTaskLog
from app.repositories.base import FileTaskRepository
from app.repositories.sqlite_utils import dumps_json, loads_json


class SQLiteFileTaskRepository(FileTaskRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

    def create(self, data: dict) -> FileTaskLog:
        task = FileTaskLog(**data)
        with self._session_factory() as session:
            session.add(self._to_record(task))
            session.commit()
        return task

    def update(self, task_id: str, updates: dict) -> FileTaskLog:
        with self._session_factory() as session:
            record = session.get(FileTaskRecord, task_id)
            if record is None:
                raise KeyError(task_id)
            record.updated_at = datetime.now(timezone.utc)
            for key, value in updates.items():
                if key == "plan":
                    record.plan_json = dumps_json(value)
                elif key == "validation":
                    record.validation_json = dumps_json(value)
                elif key == "execution":
                    record.execution_json = dumps_json(value)
                elif key == "undo":
                    record.undo_json = dumps_json(value)
                elif hasattr(record, key):
                    setattr(record, key, value)
            session.commit()
            session.refresh(record)
            return self._to_task(record)

    def get(self, task_id: str) -> FileTaskLog | None:
        with self._session_factory() as session:
            record = session.get(FileTaskRecord, task_id)
            return self._to_task(record) if record else None

    def list_recent(self, limit: int = 20) -> list[FileTaskLog]:
        with self._session_factory() as session:
            records = session.scalars(select(FileTaskRecord).order_by(FileTaskRecord.created_at.desc()).limit(limit)).all()
            return [self._to_task(record) for record in records]

    def clear(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(FileTaskRecord))
            session.commit()

    def count(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(FileTaskRecord)) or 0)

    def _to_record(self, task: FileTaskLog) -> FileTaskRecord:
        return FileTaskRecord(
            id=task.id,
            root_path=task.root_path,
            instruction=task.instruction,
            status=task.status,
            plan_json=dumps_json(task.plan),
            validation_json=dumps_json(task.validation),
            execution_json=dumps_json(task.execution) if task.execution is not None else None,
            undo_json=dumps_json(task.undo),
            created_at=task.created_at,
            updated_at=task.updated_at,
            executed_at=task.executed_at,
            undone_at=task.undone_at,
        )

    def _to_task(self, record: FileTaskRecord) -> FileTaskLog:
        return FileTaskLog(
            id=record.id,
            root_path=record.root_path,
            instruction=record.instruction,
            status=record.status,
            plan=loads_json(record.plan_json, {}),
            validation=loads_json(record.validation_json, {}),
            execution=loads_json(record.execution_json, None),
            undo=loads_json(record.undo_json, []),
            created_at=record.created_at,
            updated_at=record.updated_at,
            executed_at=record.executed_at,
            undone_at=record.undone_at,
        )
