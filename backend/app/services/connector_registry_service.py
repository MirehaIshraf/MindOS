import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.database import AppSettingRecord, get_session_factory, initialize_database
from app.core.dependencies import get_connector_source_repository, get_event_repository
from app.repositories.base import ConnectorSourceRepository, EventRepository
from app.schemas.connectors import (
    ConnectorConfigResponse,
    ConnectorListResponse,
    ConnectorStatusResponse,
    ConnectorToggleResponse,
    VSCodeConnectorRuntimeResponse,
    VSCodeHeartbeatRequest,
    VSCodeHeartbeatResponse,
)

VSCODE_ACCEPTED_EVENT_TYPES = [
    "editor_workspace_opened",
    "editor_file_saved",
    "editor_file_opened",
    "editor_terminal_command",
]

VSCODE_RUNTIME_DEFAULTS = {
    "capture_file_open": False,
    "capture_file_save": True,
    "capture_workspace_open": True,
    "capture_terminal_commands": False,
    "include_file_content_on_save": False,
    "max_content_chars": 2000,
}


@dataclass(frozen=True)
class ConnectorDefinition:
    id: str
    name: str
    type: str
    description: str
    default_enabled: bool
    configured_by_default: bool
    supports_toggle: bool
    supports_config: bool
    supports_manual_import: bool
    supports_live_events: bool
    event_source: str | None = None


CONNECTOR_DEFINITIONS = [
    ConnectorDefinition(
        id="vscode",
        name="VSCode",
        type="vscode",
        description="Capture selected editor and workspace activity.",
        default_enabled=False,
        configured_by_default=True,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=False,
        supports_live_events=True,
        event_source="vscode_extension",
    ),
    ConnectorDefinition(
        id="browser",
        name="Browser",
        type="browser",
        description="Capture selected research pages and browsing context.",
        default_enabled=False,
        configured_by_default=False,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=False,
        supports_live_events=True,
        event_source="browser_extension",
    ),
    ConnectorDefinition(
        id="github",
        name="GitHub",
        type="github",
        description="Import repositories, issues, pull requests, and reviews.",
        default_enabled=False,
        configured_by_default=False,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=False,
        supports_live_events=False,
        event_source="github",
    ),
    ConnectorDefinition(
        id="jira",
        name="Jira",
        type="jira",
        description="Import tickets and project activity.",
        default_enabled=False,
        configured_by_default=False,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=False,
        supports_live_events=False,
        event_source="jira",
    ),
    ConnectorDefinition(
        id="email",
        name="Email",
        type="email",
        description="Import selected email context.",
        default_enabled=False,
        configured_by_default=False,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=False,
        supports_live_events=False,
        event_source="email",
    ),
    ConnectorDefinition(
        id="file_system",
        name="File System",
        type="file_system",
        description="Import local folders and files.",
        default_enabled=True,
        configured_by_default=True,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=True,
        supports_live_events=False,
        event_source="file_system",
    ),
    ConnectorDefinition(
        id="logs",
        name="Logs",
        type="logs",
        description="Import local log files.",
        default_enabled=True,
        configured_by_default=True,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=True,
        supports_live_events=False,
        event_source="logs",
    ),
    ConnectorDefinition(
        id="git",
        name="Local Git",
        type="git",
        description="Import local repository commits and status.",
        default_enabled=True,
        configured_by_default=True,
        supports_toggle=True,
        supports_config=True,
        supports_manual_import=True,
        supports_live_events=False,
        event_source="git",
    ),
]


class ConnectorRegistryService:
    def __init__(
        self,
        event_repository: EventRepository | None = None,
        source_repository: ConnectorSourceRepository | None = None,
    ) -> None:
        self._event_repository = event_repository or get_event_repository()
        self._source_repository = source_repository or get_connector_source_repository()

    def list_connectors(self) -> ConnectorListResponse:
        return ConnectorListResponse(connectors=[self.get_connector(definition.id) for definition in CONNECTOR_DEFINITIONS])

    def get_connector(self, connector_id: str) -> ConnectorStatusResponse:
        definition = self._definition(connector_id)
        enabled = self.is_enabled(definition.id)
        config = self.get_config_dict(definition.id)
        configured = definition.configured_by_default or bool(config)
        events = self._events_for_source(definition.event_source)
        last_event_at = max((event.timestamp for event in events), default=None)
        heartbeat = self._get_heartbeat(definition.id) if definition.supports_live_events else {}
        heartbeat_seen_at = _parse_datetime(heartbeat.get("last_seen_at"))
        last_seen_at = _latest_datetime([heartbeat_seen_at, last_event_at]) if definition.supports_live_events else None
        connected = self._connected(definition, enabled, configured, last_seen_at)
        status = self._status(definition, enabled, configured, connected, last_seen_at)
        saved_sources = [
            source for source in self._source_repository.list_sources() if source.connector_type == definition.id
        ] if definition.supports_manual_import else []
        summary = {
            "saved_sources_count": len(saved_sources),
        }
        latest_import = sorted(
            [source for source in saved_sources if source.last_import_at],
            key=lambda source: source.last_import_at,
            reverse=True,
        )
        if latest_import:
            summary["last_import_at"] = latest_import[0].last_import_at.isoformat()
            summary["last_import_status"] = latest_import[0].last_import_status
        if config:
            summary["configured_keys"] = sorted(config.keys())
        if heartbeat:
            summary["client_id"] = heartbeat.get("client_id")
            summary["extension_version"] = heartbeat.get("extension_version")
            summary["workspace_name"] = heartbeat.get("workspace_name")
        return ConnectorStatusResponse(
            id=definition.id,
            name=definition.name,
            type=definition.type,
            description=definition.description,
            enabled=enabled,
            configured=configured,
            connected=connected,
            status=status,
            event_count=len(events),
            last_event_at=last_event_at,
            last_seen_at=last_seen_at,
            config_summary=summary,
            supports_toggle=definition.supports_toggle,
            supports_config=definition.supports_config,
            supports_manual_import=definition.supports_manual_import,
            supports_live_events=definition.supports_live_events,
        )

    def set_enabled(self, connector_id: str, enabled: bool) -> ConnectorToggleResponse:
        definition = self._definition(connector_id)
        self._set_setting(f"connector.{definition.id}.enabled", enabled)
        connector = self.get_connector(definition.id)
        return ConnectorToggleResponse(
            id=definition.id,
            enabled=enabled,
            status=connector.status,
            message=f"{definition.name} connector {'enabled' if enabled else 'disabled'}.",
        )

    def is_enabled(self, connector_id: str) -> bool:
        definition = self._definition(connector_id)
        return bool(self._get_setting(f"connector.{definition.id}.enabled", definition.default_enabled))

    def get_config(self, connector_id: str) -> ConnectorConfigResponse:
        definition = self._definition(connector_id)
        config = self.get_config_dict(definition.id)
        return ConnectorConfigResponse(
            id=definition.id,
            config=config,
            configured=definition.configured_by_default or bool(config),
        )

    def save_config(self, connector_id: str, config: dict[str, Any]) -> ConnectorConfigResponse:
        definition = self._definition(connector_id)
        self._set_setting(f"connector.{definition.id}.config", config)
        return self.get_config(definition.id)

    def get_vscode_runtime(self) -> VSCodeConnectorRuntimeResponse:
        connector = self.get_connector("vscode")
        config = {**VSCODE_RUNTIME_DEFAULTS, **self.get_config_dict("vscode")}
        return VSCodeConnectorRuntimeResponse(
            enabled=connector.enabled,
            configured=connector.configured,
            status=connector.status,
            accepted_event_types=VSCODE_ACCEPTED_EVENT_TYPES,
            capture_file_open=bool(config.get("capture_file_open", False)),
            capture_file_save=bool(config.get("capture_file_save", True)),
            capture_workspace_open=bool(config.get("capture_workspace_open", True)),
            capture_terminal_commands=bool(config.get("capture_terminal_commands", False)),
            include_file_content_on_save=bool(config.get("include_file_content_on_save", False)),
            max_content_chars=int(config.get("max_content_chars", 2000) or 2000),
        )

    def record_vscode_heartbeat(self, request: VSCodeHeartbeatRequest) -> VSCodeHeartbeatResponse:
        payload = {
            "client_id": request.client_id,
            "extension_version": request.extension_version,
            "workspace_name": request.workspace_name,
            "workspace_folders": request.workspace_folders,
            "session_id": request.session_id,
            "status": request.status,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
        self._set_setting("connector.vscode.heartbeat", payload)
        return VSCodeHeartbeatResponse(connector_enabled=self.is_enabled("vscode"))

    def record_seen(self, connector_id: str, metadata: dict[str, Any] | None = None) -> None:
        definition = self._definition(connector_id)
        payload = {
            **self._get_heartbeat(definition.id),
            **(metadata or {}),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
        self._set_setting(f"connector.{definition.id}.heartbeat", payload)

    def get_config_dict(self, connector_id: str) -> dict[str, Any]:
        value = self._get_setting(f"connector.{connector_id}.config", {})
        return value if isinstance(value, dict) else {}

    def _get_heartbeat(self, connector_id: str) -> dict[str, Any]:
        value = self._get_setting(f"connector.{connector_id}.heartbeat", {})
        return value if isinstance(value, dict) else {}

    def _events_for_source(self, source: str | None) -> list[Any]:
        if not source:
            return []
        return [
            event
            for event in self._event_repository.list_all_events(include_hidden=True)
            if event.source.value == source
        ]

    def _connected(
        self,
        definition: ConnectorDefinition,
        enabled: bool,
        configured: bool,
        last_seen_at: datetime | None,
    ) -> bool:
        if not enabled or not configured:
            return False
        if definition.supports_manual_import:
            return True
        if definition.id == "vscode" and last_seen_at:
            return _aware(last_seen_at) >= datetime.now(timezone.utc) - timedelta(minutes=2)
        return False

    def _status(
        self,
        definition: ConnectorDefinition,
        enabled: bool,
        configured: bool,
        connected: bool,
        last_seen_at: datetime | None,
    ) -> str:
        if not enabled:
            return "off"
        if not configured:
            return "needs_configuration"
        if connected:
            return "connected"
        if definition.id == "vscode":
            return "disconnected"
        if definition.supports_live_events:
            return "disconnected" if last_seen_at else "needs_configuration"
        return "connected"

    def _definition(self, connector_id: str) -> ConnectorDefinition:
        normalized = connector_id.strip().lower().replace("-", "_")
        for definition in CONNECTOR_DEFINITIONS:
            if definition.id == normalized:
                return definition
        raise KeyError(f"Unknown connector: {connector_id}")

    def _get_setting(self, key: str, default: Any) -> Any:
        initialize_database()
        with get_session_factory()() as session:
            record = session.get(AppSettingRecord, key)
            if record is None:
                return default
            try:
                return json.loads(record.value)
            except json.JSONDecodeError:
                return default

    def _set_setting(self, key: str, value: Any) -> None:
        initialize_database()
        with get_session_factory()() as session:
            record = session.get(AppSettingRecord, key)
            if record is None:
                record = AppSettingRecord(key=key, value=json.dumps(value), updated_at=datetime.now(timezone.utc))
                session.add(record)
            else:
                record.value = json.dumps(value)
                record.updated_at = datetime.now(timezone.utc)
            session.commit()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _latest_datetime(values: list[datetime | None]) -> datetime | None:
    available = [_aware(value) for value in values if value is not None]
    if not available:
        return None
    return max(available)


connector_registry_service = ConnectorRegistryService()
