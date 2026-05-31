from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.domain.models import Event
from app.repositories.base import EventRepository
from app.schemas.ingest import (
    CollectorClientResponse,
    ExternalEventIngestRequest,
    ExternalIngestResponse,
)
from app.services.connector_registry_service import connector_registry_service
from app.services.relationship_service import relationship_service

SUPPORTED_EXTERNAL_SOURCES = [
    "vscode_extension",
    "browser_extension",
    "activity_tracker",
    "local_agent",
]

PREFERRED_EXTERNAL_EVENT_TYPES = {
    "vscode_extension": [
        "editor_file_opened",
        "editor_file_saved",
        "editor_file_modified",
        "editor_workspace_opened",
        "editor_terminal_command",
        "editor_debug_started",
        "editor_debug_stopped",
    ],
    "browser_extension": [
        "browser_page_saved",
        "browser_selection_saved",
        "browser_research_note",
    ],
    "activity_tracker": [
        "app_focus_changed",
        "active_window_changed",
        "idle_started",
        "idle_ended",
        "work_session_started",
        "work_session_ended",
    ],
    "local_agent": [
        "agent_observation",
        "agent_summary",
        "agent_decision",
        "agent_action_preview",
        "agent_action_result",
    ],
}

EXTERNAL_SOURCE_TO_CONNECTOR = {
    "vscode_extension": "vscode",
    "browser_extension": "browser",
}


class ExternalIngestService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()

    def ingest_event(self, request: ExternalEventIngestRequest) -> ExternalIngestResponse:
        event = self._create_event(request)
        return ExternalIngestResponse(
            status="ingested",
            event_id=event.id,
            message=f"Ingested external {event.source.value} event.",
        )

    def ingest_event_raw(self, request: ExternalEventIngestRequest) -> Event:
        return self._create_event(request)

    def collector_clients(self) -> list[CollectorClientResponse]:
        clients: dict[tuple[str, str], dict[str, Any]] = {}
        for event in self._external_events():
            client_id = str(event.metadata.get("client_id") or f"{event.source.value}-local")
            key = (event.source.value, client_id)
            current = clients.setdefault(
                key,
                {
                    "id": client_id,
                    "name": str(event.metadata.get("client_name") or self._default_client_name(event.source.value)),
                    "type": event.source.value,
                    "enabled": True,
                    "last_seen_at": event.timestamp,
                    "events_count": 0,
                },
            )
            current["events_count"] += 1
            if event.timestamp > current["last_seen_at"]:
                current["last_seen_at"] = event.timestamp
        self._merge_heartbeat_client(clients, "vscode_extension", "vscode", "VSCode Extension")
        self._merge_heartbeat_client(clients, "browser_extension", "browser", "Browser Extension")
        return [
            CollectorClientResponse(**client)
            for client in sorted(clients.values(), key=lambda item: item["last_seen_at"] or datetime.min, reverse=True)
        ]

    def _merge_heartbeat_client(
        self,
        clients: dict[tuple[str, str], dict[str, Any]],
        source: str,
        connector_id: str,
        default_name: str,
    ) -> None:
        try:
            heartbeat = connector_registry_service.heartbeat_metadata(connector_id)
        except Exception:
            return
        seen_at = _parse_datetime(heartbeat.get("last_seen_at"))
        if not seen_at:
            return
        client_id = str(heartbeat.get("client_id") or f"{source}-local")
        key = (source, client_id)
        current = clients.setdefault(
            key,
            {
                "id": client_id,
                "name": default_name,
                "type": source,
                "enabled": connector_registry_service.is_enabled(connector_id),
                "last_seen_at": seen_at,
                "events_count": 0,
            },
        )
        current["enabled"] = connector_registry_service.is_enabled(connector_id)
        if _aware(seen_at) > _aware(current["last_seen_at"]):
            current["last_seen_at"] = seen_at

    def recent_external_events_count(self, hours: int = 24) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return sum(1 for event in self._external_events() if _aware(event.timestamp) >= cutoff)

    def _create_event(self, request: ExternalEventIngestRequest) -> Event:
        source_value = self._normalize_source(request.source)
        self._ensure_connector_enabled(source_value)
        event_type = self._normalize_type(request.type)
        metadata = self._normalize_metadata(source_value, request)
        title = request.title.strip() or self._default_title(source_value, event_type, metadata)
        event = self._event_repository.create_event(
            {
                "source": EventSource(source_value),
                "type": event_type,
                "title": title,
                "content": request.content or "",
                "metadata": metadata,
                "timestamp": request.timestamp or datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        try:
            relationship_service.detect_relationships_for_event(event)
        except Exception:
            pass
        self._record_connector_seen(source_value, metadata)
        return event

    def _ensure_connector_enabled(self, source: str) -> None:
        connector_id = EXTERNAL_SOURCE_TO_CONNECTOR.get(source)
        if not connector_id:
            return
        if not connector_registry_service.is_enabled(connector_id):
            connector_name = connector_registry_service.get_connector(connector_id).name
            raise PermissionError(f"{connector_name} connector is disabled in MindOS.")

    def _record_connector_seen(self, source: str, metadata: dict[str, Any]) -> None:
        connector_id = EXTERNAL_SOURCE_TO_CONNECTOR.get(source)
        if not connector_id:
            return
        try:
            connector_registry_service.record_seen(
                connector_id,
                {
                    "client_id": metadata.get("client_id"),
                    "session_id": metadata.get("session_id"),
                    "workspace_name": metadata.get("workspace_name"),
                },
            )
        except Exception:
            pass

    def _external_events(self) -> list[Event]:
        return [
            event
            for event in self._event_repository.list_all_events(include_hidden=True)
            if event.source.value in SUPPORTED_EXTERNAL_SOURCES
        ]

    def _normalize_source(self, source: str) -> str:
        source_value = (source or "").strip().lower().replace("-", "_")
        if source_value not in SUPPORTED_EXTERNAL_SOURCES:
            raise ValueError(f"Unsupported external source: {source}")
        return source_value

    def _normalize_type(self, event_type: str) -> str:
        normalized = (event_type or "").strip().lower().replace(" ", "_").replace("-", "_")
        if not normalized:
            raise ValueError("External event type is required.")
        return normalized

    def _normalize_metadata(self, source: str, request: ExternalEventIngestRequest) -> dict[str, Any]:
        metadata = dict(request.metadata or {})
        metadata["external_ingest"] = True
        metadata["collector_source"] = source
        if request.client_id:
            metadata["client_id"] = request.client_id
        else:
            metadata.setdefault("client_id", f"{source}-local")
        if request.session_id:
            metadata["session_id"] = request.session_id
        return metadata

    def _default_title(self, source: str, event_type: str, metadata: dict[str, Any]) -> str:
        if source == "vscode_extension":
            return str(metadata.get("file_path") or metadata.get("workspace_path") or event_type.replace("_", " ").title())
        if source == "browser_extension":
            return str(metadata.get("page_title") or metadata.get("url") or event_type.replace("_", " ").title())
        if source == "activity_tracker":
            return str(metadata.get("window_title") or metadata.get("app_name") or event_type.replace("_", " ").title())
        if source == "local_agent":
            return str(metadata.get("summary") or event_type.replace("_", " ").title())
        return event_type.replace("_", " ").title()

    def _default_client_name(self, source: str) -> str:
        return {
            "vscode_extension": "VSCode Extension",
            "browser_extension": "Browser Extension",
            "activity_tracker": "Activity Tracker",
            "local_agent": "Local Agent",
        }.get(source, source.replace("_", " ").title())


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


external_ingest_service = ExternalIngestService()
