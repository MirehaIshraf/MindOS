from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4

from app.core.dependencies import get_connector_source_repository
from app.domain.models import ConnectorSource
from app.repositories.base import ConnectorSourceRepository
from app.schemas.file_index import FileIndexJobResponse, FileIndexJobsResponse
from app.services.connector_source_service import connector_source_service


DEFAULT_INDEX_INTERVAL_MINUTES = 20
POLL_SECONDS = 30
MAX_JOBS = 100


class FileIndexSchedulerService:
    def __init__(self, source_repository: ConnectorSourceRepository | None = None) -> None:
        self._sources = source_repository or get_connector_source_repository()
        self._lock = Lock()
        self._stop = Event()
        self._wake = Event()
        self._started = False
        self._queue: list[str] = []
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        Thread(target=self._loop, name="mindos-file-index-scheduler", daemon=True).start()

    def queue_source(self, source_id: str, reason: str = "manual") -> FileIndexJobResponse:
        source = self._sources.get_source(source_id)
        if source is None:
            raise KeyError("Tracked folder not found.")
        if source.connector_type != "file_system":
            raise ValueError("Only File System tracked folders can be indexed.")
        if not source.enabled or (source.config or {}).get("indexing_enabled") is not True:
            raise ValueError("This tracked folder is disabled.")

        with self._lock:
            existing = self._active_job_for_source(source_id)
            if existing is not None:
                return self._job_response(existing)
            now = self._now()
            job = {
                "job_id": str(uuid4()),
                "source_id": source_id,
                "status": "queued",
                "reason": reason,
                "message": "Queued for background indexing.",
                "queued_at": now,
                "started_at": None,
                "completed_at": None,
                "error": None,
                "result": None,
            }
            self._jobs[job["job_id"]] = job
            self._queue.append(job["job_id"])
            self._trim_jobs_locked()
            self._wake.set()
        self._set_source_index_status(source_id, "queued", None)
        return self._job_response(job)

    def queue_stale_sources(self) -> int:
        queued = 0
        now = datetime.now(timezone.utc)
        for source in self._sources.list_sources(connector_type="file_system"):
            config = source.config or {}
            if not source.enabled or config.get("indexing_enabled") is not True:
                continue
            if self._has_active_job(source.id):
                continue
            next_index_after = self._parse_datetime(config.get("next_index_after"))
            last_indexed_at = self._parse_datetime(config.get("last_indexed_at"))
            if last_indexed_at is None or next_index_after is None or next_index_after <= now:
                self.queue_source(source.id, reason="scheduled")
                queued += 1
        return queued

    def list_jobs(self) -> FileIndexJobsResponse:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item["queued_at"], reverse=True)
            return FileIndexJobsResponse(jobs=[self._job_response(job) for job in jobs], total=len(jobs))

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.queue_stale_sources()
                job_id = self._next_job_id()
                if job_id:
                    self._run_job(job_id)
                    continue
            except Exception:
                pass
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()

    def _next_job_id(self) -> str | None:
        with self._lock:
            if not self._queue:
                return None
            return self._queue.pop(0)

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["status"] = "running"
            job["message"] = "Indexing connected folder in the background."
            job["started_at"] = self._now()
            source_id = job["source_id"]
        self._set_source_index_status(source_id, "indexing", None)
        try:
            result = connector_source_service.index_source(source_id)
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "completed"
                job["message"] = "Background indexing completed."
                job["completed_at"] = self._now()
                job["result"] = result.get("result") if isinstance(result, dict) else result
            self._set_source_index_status(source_id, "idle", None, completed=True)
        except Exception as error:
            message = str(error)
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "failed"
                job["message"] = "Background indexing failed."
                job["completed_at"] = self._now()
                job["error"] = message
            self._set_source_index_status(source_id, "error", message)

    def _set_source_index_status(self, source_id: str, status: str, error: str | None, completed: bool = False) -> None:
        source = self._sources.get_source(source_id)
        if source is None:
            return
        config = dict(source.config or {})
        config["index_status"] = status
        config["last_error"] = error
        if completed:
            interval = self._index_interval_minutes(source)
            config["next_index_after"] = (datetime.now(timezone.utc) + timedelta(minutes=interval)).isoformat()
        self._sources.update_source(source_id, {"config": config})

    def _active_job_for_source(self, source_id: str) -> dict[str, Any] | None:
        for job in self._jobs.values():
            if job["source_id"] == source_id and job["status"] in {"queued", "running"}:
                return job
        return None

    def _has_active_job(self, source_id: str) -> bool:
        with self._lock:
            return self._active_job_for_source(source_id) is not None

    def _index_interval_minutes(self, source: ConnectorSource) -> int:
        try:
            value = int((source.config or {}).get("index_interval_minutes", DEFAULT_INDEX_INTERVAL_MINUTES))
        except (TypeError, ValueError):
            value = DEFAULT_INDEX_INTERVAL_MINUTES
        return max(10, min(value, 30))

    def _trim_jobs_locked(self) -> None:
        if len(self._jobs) <= MAX_JOBS:
            return
        completed = sorted(
            [job for job in self._jobs.values() if job["status"] not in {"queued", "running"}],
            key=lambda item: item["queued_at"],
        )
        while len(self._jobs) > MAX_JOBS and completed:
            old = completed.pop(0)
            self._jobs.pop(old["job_id"], None)

    def _job_response(self, job: dict[str, Any]) -> FileIndexJobResponse:
        return FileIndexJobResponse(**job)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None


file_index_scheduler_service = FileIndexSchedulerService()
