from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.database import ChatRunRecord, get_session_factory, initialize_database
from app.domain.models import ChatRun
from app.repositories.base import ChatRunRepository
from app.repositories.sqlite_utils import dumps_json, loads_json


ACTIVE_RUN_STATUSES = {"queued", "running"}


class SQLiteChatRunRepository(ChatRunRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

    def create_run(self, data: dict) -> ChatRun:
        run = ChatRun(**data)
        with self._session_factory() as session:
            session.add(self._to_record(run))
            session.commit()
        return run

    def update_run(self, run_id: str, updates: dict) -> ChatRun:
        with self._session_factory() as session:
            record = session.get(ChatRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            for key, value in updates.items():
                if key == "result_json":
                    record.result_json = dumps_json(value) if value is not None else None
                elif key == "metadata_json":
                    record.metadata_json = dumps_json(value or {})
                elif key == "progress_events":
                    record.progress_events_json = dumps_json(value or [])
                elif hasattr(record, key):
                    setattr(record, key, value)
            session.commit()
            return self._to_run(record)

    def update_progress(self, run_id: str, step: str, message: str, progress_percent: int | None = None) -> ChatRun:
        return self.update_run(
            run_id,
            {
                "current_step": step,
                "progress_message": message,
                "progress_percent": progress_percent,
            },
        )

    def append_progress_event(self, run_id: str, step: str, message: str, level: str = "info") -> ChatRun:
        with self._session_factory() as session:
            record = session.get(ChatRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            events = loads_json(record.progress_events_json, [])
            event = {
                "step": step,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
            }
            record.progress_events_json = dumps_json([*events, event][-20:])
            session.commit()
            return self._to_run(record)

    def get_run(self, run_id: str) -> ChatRun | None:
        with self._session_factory() as session:
            record = session.get(ChatRunRecord, run_id)
            return self._to_run(record) if record else None

    def get_active_run(self, session_id: str) -> ChatRun | None:
        with self._session_factory() as session:
            record = session.scalars(
                select(ChatRunRecord)
                .where(ChatRunRecord.session_id == session_id)
                .where(ChatRunRecord.status.in_(ACTIVE_RUN_STATUSES))
                .order_by(ChatRunRecord.started_at.desc())
                .limit(1)
            ).first()
            return self._to_run(record) if record else None

    def get_latest_run(self, session_id: str) -> ChatRun | None:
        with self._session_factory() as session:
            record = session.scalars(
                select(ChatRunRecord)
                .where(ChatRunRecord.session_id == session_id)
                .order_by(ChatRunRecord.started_at.desc())
                .limit(1)
            ).first()
            return self._to_run(record) if record else None

    def list_recent_runs(self, limit: int = 20) -> list[ChatRun]:
        with self._session_factory() as session:
            records = session.scalars(select(ChatRunRecord).order_by(ChatRunRecord.started_at.desc()).limit(limit)).all()
            return [self._to_run(record) for record in records]

    def cancel_run(self, run_id: str) -> ChatRun:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        metadata = dict(run.metadata_json or {})
        metadata["cancellation_requested"] = True
        updates = {"metadata_json": metadata}
        if run.status == "queued":
            updates.update({"status": "cancelled", "completed_at": datetime.now(timezone.utc)})
        return self.update_run(run_id, updates)

    def clear_runs(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(ChatRunRecord))
            session.commit()

    def _to_record(self, run: ChatRun) -> ChatRunRecord:
        return ChatRunRecord(
            id=run.id,
            session_id=run.session_id,
            user_message_id=run.user_message_id,
            assistant_message_id=run.assistant_message_id,
            status=run.status,
            user_message=run.user_message,
            resolved_query=run.resolved_query,
            model_id=run.model_id,
            provider=run.provider,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error=run.error,
            result_json=dumps_json(run.result_json) if run.result_json is not None else None,
            metadata_json=dumps_json(run.metadata_json or {}),
            current_step=run.current_step,
            progress_message=run.progress_message,
            progress_percent=run.progress_percent,
            progress_events_json=dumps_json(run.progress_events or []),
        )

    def _to_run(self, record: ChatRunRecord) -> ChatRun:
        return ChatRun(
            id=record.id,
            session_id=record.session_id,
            user_message_id=record.user_message_id,
            assistant_message_id=record.assistant_message_id,
            status=record.status,
            user_message=record.user_message,
            resolved_query=record.resolved_query,
            model_id=record.model_id,
            provider=record.provider,
            started_at=record.started_at,
            completed_at=record.completed_at,
            error=record.error,
            result_json=loads_json(record.result_json, None),
            metadata_json=loads_json(record.metadata_json, {}),
            current_step=record.current_step,
            progress_message=record.progress_message,
            progress_percent=record.progress_percent,
            progress_events=loads_json(record.progress_events_json, []),
        )
