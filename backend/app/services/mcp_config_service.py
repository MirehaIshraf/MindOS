from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.database import AppSettingRecord, get_session_factory


FILESYSTEM_MCP_CONFIG_KEY = "mcp.filesystem.config"

DEFAULT_FILESYSTEM_MCP_CONFIG: dict[str, Any] = {
    "root_path": "",
    "max_depth": 5,
    "max_files": 2000,
    "recursive": True,
    "index_readable_files": True,
    "index_status": "idle",
    "indexed_count": 0,
    "inventory_count": 0,
    "missing_count": 0,
    "last_indexed_at": None,
    "last_error": None,
    "watch_status": "idle",
    "last_watch_event_at": None,
}


class McpConfigService:
    def __init__(self) -> None:
        self._session_factory = None

    def get_filesystem_config(self) -> dict[str, Any]:
        config = dict(DEFAULT_FILESYSTEM_MCP_CONFIG)
        saved = self._get_json(FILESYSTEM_MCP_CONFIG_KEY)
        if isinstance(saved, dict):
            config.update(saved)
        return self._normalize_filesystem_config(config)

    def save_filesystem_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        config = self.get_filesystem_config()
        config.update({key: value for key, value in updates.items() if value is not None})
        normalized = self._normalize_filesystem_config(config)
        self._set_json(FILESYSTEM_MCP_CONFIG_KEY, normalized)
        return normalized

    def update_filesystem_status(self, updates: dict[str, Any]) -> dict[str, Any]:
        return self.save_filesystem_config(updates)

    def _get_json(self, key: str) -> Any:
        with self._sessions() as session:
            record = session.get(AppSettingRecord, key)
            if record is None:
                return None
            try:
                return json.loads(record.value)
            except json.JSONDecodeError:
                return None

    def _set_json(self, key: str, value: Any) -> None:
        with self._sessions() as session:
            record = session.get(AppSettingRecord, key)
            encoded = json.dumps(value)
            now = datetime.now(timezone.utc)
            if record is None:
                record = AppSettingRecord(key=key, value=encoded, updated_at=now)
                session.add(record)
            else:
                record.value = encoded
                record.updated_at = now
            session.commit()

    def _sessions(self):
        if self._session_factory is None:
            self._session_factory = get_session_factory()
        return self._session_factory()

    def _normalize_filesystem_config(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(DEFAULT_FILESYSTEM_MCP_CONFIG)
        normalized.update(config)
        normalized["root_path"] = str(normalized.get("root_path") or "").strip()
        normalized["max_depth"] = _clamp_int(normalized.get("max_depth"), 0, 10, 5)
        normalized["max_files"] = _clamp_int(normalized.get("max_files"), 1, 5000, 2000)
        normalized["recursive"] = bool(normalized.get("recursive", True))
        normalized["index_readable_files"] = bool(normalized.get("index_readable_files", True))
        normalized["indexed_count"] = _clamp_int(normalized.get("indexed_count"), 0, 1_000_000, 0)
        normalized["inventory_count"] = _clamp_int(normalized.get("inventory_count"), 0, 1_000_000, 0)
        normalized["missing_count"] = _clamp_int(normalized.get("missing_count"), 0, 1_000_000, 0)
        return normalized


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


mcp_config_service = McpConfigService()
