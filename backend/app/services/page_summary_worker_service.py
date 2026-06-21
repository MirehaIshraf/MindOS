from __future__ import annotations

from threading import Event as ThreadEvent, Lock, Thread

from app.core.dependencies import get_event_repository
from app.repositories.base import EventRepository

POLL_SECONDS = 45
SWEEP_BATCH = 5


class PageSummaryWorkerService:
    """Background worker that LLM-summarizes browser captures off the request path.

    Captures are enqueued on ingest; a periodic sweep also picks up any pages still
    at summary_status="pending" so the backlog gets cleared over time. Summaries run
    one at a time so the local model is never overloaded.
    """

    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._events = event_repository or get_event_repository()
        self._lock = Lock()
        self._queue: list[str] = []
        self._queued: set[str] = set()
        self._stop = ThreadEvent()
        self._wake = ThreadEvent()
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        Thread(target=self._loop, name="mindos-page-summary-worker", daemon=True).start()

    def enqueue(self, event_id: str) -> None:
        if not event_id:
            return
        with self._lock:
            if event_id in self._queued:
                return
            self._queued.add(event_id)
            self._queue.append(event_id)
        self._wake.set()

    def _loop(self) -> None:
        from app.services.browser_memory_service import browser_memory_service

        while not self._stop.is_set():
            try:
                self._sweep_pending()
                event_id = self._next()
                if event_id:
                    try:
                        browser_memory_service.auto_summarize_browser_page(event_id)
                    except Exception:
                        pass
                    continue
            except Exception:
                pass
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()

    def _next(self) -> str | None:
        with self._lock:
            if not self._queue:
                return None
            event_id = self._queue.pop(0)
            self._queued.discard(event_id)
            return event_id

    def _sweep_pending(self) -> None:
        count = 0
        for event in self._events.list_all_events(include_hidden=True):
            if count >= SWEEP_BATCH:
                break
            if event.source.value != "browser_extension" or event.type != "browser_page_captured":
                continue
            if (event.metadata or {}).get("summary_status") != "pending":
                continue
            self.enqueue(event.id)
            count += 1


page_summary_worker_service = PageSummaryWorkerService()
