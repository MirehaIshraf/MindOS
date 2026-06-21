from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread, Timer
from typing import Any

from app.services.mcp_config_service import mcp_config_service


class McpFileWatchService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._observer: Any | None = None
        self._root_path: str | None = None
        self._timer: Timer | None = None
        self._running = False

    def start_for_config(self) -> None:
        config = mcp_config_service.get_filesystem_config()
        root_path = str(config.get("root_path") or "").strip()
        if not root_path:
            self.stop()
            mcp_config_service.update_filesystem_status({"watch_status": "idle"})
            return
        self.start(root_path)

    def start(self, root_path: str) -> None:
        root = Path(root_path).resolve()
        if not root.exists() or not root.is_dir():
            self.stop()
            mcp_config_service.update_filesystem_status({"watch_status": "error", "last_error": "MCP root path is not watchable."})
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception:
            mcp_config_service.update_filesystem_status({"watch_status": "unavailable", "last_error": "watchdog is not installed."})
            return

        service = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):  # type: ignore[override]
                if getattr(event, "is_directory", False):
                    return
                service.schedule_index("watch")

        with self._lock:
            if self._root_path == str(root) and self._observer is not None:
                return
            self._stop_locked()
            observer = Observer()
            observer.schedule(Handler(), str(root), recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer
            self._root_path = str(root)
            self._running = True
        mcp_config_service.update_filesystem_status({"watch_status": "watching", "last_error": None})

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
        mcp_config_service.update_filesystem_status({"watch_status": "idle"})

    def schedule_index(self, reason: str = "watch") -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = Timer(3.0, self._run_index, args=(reason,))
            self._timer.daemon = True
            self._timer.start()
        mcp_config_service.update_filesystem_status(
            {
                "watch_status": "change_detected",
                "last_watch_event_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _run_index(self, reason: str) -> None:
        Thread(target=self._index_in_thread, args=(reason,), daemon=True, name="mindos-mcp-file-index").start()

    def _index_in_thread(self, reason: str) -> None:
        try:
            from app.services.mcp_file_index_service import mcp_file_index_service

            mcp_file_index_service.index_configured_root(reason=reason)
            mcp_config_service.update_filesystem_status({"watch_status": "watching"})
        except Exception as error:
            mcp_config_service.update_filesystem_status({"watch_status": "error", "last_error": str(error)})

    def _stop_locked(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
        self._observer = None
        self._root_path = None
        self._running = False


mcp_file_watch_service = McpFileWatchService()
