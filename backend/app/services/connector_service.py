from app.core.dependencies import get_event_repository
from app.repositories.base import EventRepository
from app.schemas.connectors import ConnectorListResponse, ConnectorStatus


class ConnectorService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()

    def list_connectors(self) -> ConnectorListResponse:
        file_events = [
            event
            for event in self._event_repository.list_all_events(include_hidden=True)
            if event.source.value == "file_system"
        ]
        file_events.sort(key=lambda event: event.timestamp, reverse=True)
        last_event_at = file_events[0].timestamp.isoformat() if file_events else None
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
                        ("logs", "Logs", "Local log import/watcher. Coming later."),
                        ("email", "Email", "Email connector. Coming later."),
                    ]
                ],
            ]
        )
