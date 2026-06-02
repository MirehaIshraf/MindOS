from datetime import datetime, timezone

from app.domain.models import ChatRun
from app.repositories.base import ChatRunRepository


ACTIVE_RUN_STATUSES = {"queued", "running"}


class MemoryChatRunRepository(ChatRunRepository):
    def __init__(self) -> None:
        self._runs: dict[str, ChatRun] = {}

    def create_run(self, data: dict) -> ChatRun:
        run = ChatRun(**data)
        self._runs[run.id] = run
        return run

    def update_run(self, run_id: str, updates: dict) -> ChatRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        updated = run.model_copy(update=updates)
        self._runs[run_id] = updated
        return updated

    def update_progress(self, run_id: str, step: str, message: str, progress_percent: int | None = None) -> ChatRun:
        updates = {
            "current_step": step,
            "progress_message": message,
            "progress_percent": progress_percent,
        }
        return self.update_run(run_id, updates)

    def append_progress_event(self, run_id: str, step: str, message: str, level: str = "info") -> ChatRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        event = {
            "step": step,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
        }
        events = [*(run.progress_events or []), event][-20:]
        return self.update_run(run_id, {"progress_events": events})

    def get_run(self, run_id: str) -> ChatRun | None:
        return self._runs.get(run_id)

    def get_active_run(self, session_id: str) -> ChatRun | None:
        runs = [
            run
            for run in self._runs.values()
            if run.session_id == session_id and run.status in ACTIVE_RUN_STATUSES
        ]
        runs.sort(key=lambda run: run.started_at, reverse=True)
        return runs[0] if runs else None

    def get_latest_run(self, session_id: str) -> ChatRun | None:
        runs = [run for run in self._runs.values() if run.session_id == session_id]
        runs.sort(key=lambda run: run.started_at, reverse=True)
        return runs[0] if runs else None

    def list_recent_runs(self, limit: int = 20) -> list[ChatRun]:
        runs = sorted(self._runs.values(), key=lambda run: run.started_at, reverse=True)
        return runs[:limit]

    def cancel_run(self, run_id: str) -> ChatRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        metadata = dict(run.metadata_json or {})
        metadata["cancellation_requested"] = True
        updates = {"metadata_json": metadata}
        if run.status == "queued":
            updates.update({"status": "cancelled", "completed_at": datetime.now(timezone.utc)})
        return self.update_run(run_id, updates)

    def clear_runs(self) -> None:
        self._runs.clear()


memory_chat_run_repository = MemoryChatRunRepository()


def get_memory_chat_run_repository() -> MemoryChatRunRepository:
    return memory_chat_run_repository
