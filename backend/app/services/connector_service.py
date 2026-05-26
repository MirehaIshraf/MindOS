from app.core.dependencies import get_event_repository
from app.core.dependencies import get_connector_source_repository
from app.repositories.base import EventRepository
from app.schemas.connectors import ConnectorListResponse, ConnectorStatus


class ConnectorService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()
        self._source_repository = get_connector_source_repository()

    def list_connectors(self) -> ConnectorListResponse:
        file_events = [
            event
            for event in self._event_repository.list_all_events(include_hidden=True)
            if event.source.value == "file_system"
        ]
        log_events = [
            event
            for event in self._event_repository.list_all_events(include_hidden=True)
            if event.source.value == "logs"
        ]
        git_events = [
            event
            for event in self._event_repository.list_all_events(include_hidden=True)
            if event.source.value == "git"
        ]
        file_events.sort(key=lambda event: event.timestamp, reverse=True)
        log_events.sort(key=lambda event: event.timestamp, reverse=True)
        git_events.sort(key=lambda event: event.timestamp, reverse=True)
        saved_sources = self._source_repository.list_sources()
        last_event_at = file_events[0].timestamp.isoformat() if file_events else None
        last_log_event_at = log_events[0].timestamp.isoformat() if log_events else None
        last_git_event_at = git_events[0].timestamp.isoformat() if git_events else None
        saved_by_type = {
            connector_type: [source for source in saved_sources if source.connector_type == connector_type]
            for connector_type in ["file_system", "logs", "git"]
        }
        return ConnectorListResponse(
            connectors=[
                ConnectorStatus(
                    name="file_system",
                    display_name="File System",
                    description="Import local text and code files into MindOS memory.",
                    status="available",
                    enabled=False,
                    events_count=len(file_events),
                    last_event_at=last_event_at,
                    supports_manual_import=True,
                    supports_live_watch=False,
                    saved_sources_count=len(saved_by_type["file_system"]),
                    last_import_at=latest_import_at(saved_by_type["file_system"]),
                    last_import_status=latest_import_status(saved_by_type["file_system"]),
                ),
                ConnectorStatus(
                    name="logs",
                    display_name="Logs",
                    description="Import local log files into MindOS memory.",
                    status="available",
                    enabled=False,
                    events_count=len(log_events),
                    last_event_at=last_log_event_at,
                    supports_manual_import=True,
                    supports_live_watch=False,
                    saved_sources_count=len(saved_by_type["logs"]),
                    last_import_at=latest_import_at(saved_by_type["logs"]),
                    last_import_status=latest_import_status(saved_by_type["logs"]),
                ),
                ConnectorStatus(
                    name="git",
                    display_name="Local Git",
                    description="Import commits, branches, and working tree status from a local Git repository.",
                    status="available",
                    enabled=False,
                    events_count=len(git_events),
                    last_event_at=last_git_event_at,
                    supports_manual_import=True,
                    supports_live_watch=False,
                    saved_sources_count=len(saved_by_type["git"]),
                    last_import_at=latest_import_at(saved_by_type["git"]),
                    last_import_status=latest_import_status(saved_by_type["git"]),
                ),
                *[
                    ConnectorStatus(
                        name=name,
                        display_name=display_name,
                        description=description,
                        status="coming_soon",
                        enabled=False,
                    )
                    for name, display_name, description in [
                        ("vscode", "VSCode", "Editor activity connector. Coming later."),
                        ("browser", "Browser", "Browser extension connector. Coming later."),
                        ("github", "GitHub", "GitHub commits, PRs, and issues connector. Coming later."),
                        ("jira", "Jira", "Jira ticket connector. Coming later."),
                        ("email", "Email", "Email connector. Coming later."),
                    ]
                ],
            ]
        )


def latest_import_at(sources) -> str | None:
    imported = [source.last_import_at for source in sources if source.last_import_at]
    return max(imported).isoformat() if imported else None


def latest_import_status(sources) -> str | None:
    latest = sorted([source for source in sources if source.last_import_at], key=lambda source: source.last_import_at, reverse=True)
    return latest[0].last_import_status if latest else None
