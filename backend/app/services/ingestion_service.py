from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus
from app.domain.models import Event
from app.repositories.base import EventRepository
from app.schemas.ingest import IngestEventRequest
from app.services.relationship_service import relationship_service


class IngestionService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()

    def ingest_event(self, request: IngestEventRequest) -> Event:
        event = self._event_repository.create_event(self._to_event_data(request))
        relationship_service.detect_relationships_for_event(event)
        return event

    def ingest_bulk(self, requests: list[IngestEventRequest]) -> list[Event]:
        event_data = [self._to_event_data(request) for request in requests]
        events = self._event_repository.create_events(event_data)
        for event in events:
            relationship_service.detect_relationships_for_event(event)
        return events

    def seed_sample_events(self) -> list[Event]:
        now = datetime.now(timezone.utc)
        sample_events: list[dict[str, Any]] = [
            {
                "source": "jira",
                "type": "ticket",
                "title": "Login fails after JWT token expiry",
                "content": "Users reported that login fails after deployment when the JWT token expires unexpectedly.",
            },
            {
                "source": "github",
                "type": "commit",
                "title": "Fix JWT refresh handling in auth middleware",
                "content": "Updated auth middleware to refresh expired JWT tokens before rejecting requests.",
            },
            {
                "source": "logs",
                "type": "error",
                "title": "JWT validation error in production logs",
                "content": "Auth service returned TokenExpiredError during login request after deployment.",
            },
            {
                "source": "browser",
                "type": "page_visit",
                "title": "OAuth refresh token best practices",
                "content": "Read documentation about refresh token rotation and secure session handling.",
            },
            {
                "source": "email",
                "type": "email_received",
                "title": "Deployment issue reported by QA",
                "content": "QA reported that users cannot login after the latest deployment.",
            },
            {
                "source": "vscode",
                "type": "file_modified",
                "title": "Modified auth_middleware.py",
                "content": "Changed token validation logic inside the authentication middleware.",
            },
            {
                "source": "vscode",
                "type": "terminal_command",
                "title": "Ran backend authentication tests",
                "content": "Executed pytest tests/auth/test_login.py to verify login and token refresh behavior.",
            },
            {
                "source": "github",
                "type": "pull_request",
                "title": "PR: Resolve authentication failure after deployment",
                "content": "Pull request created to fix JWT expiry handling and improve login stability.",
            },
            {
                "source": "jira",
                "type": "ticket",
                "title": "Deployment failure investigation",
                "content": "Investigate why the latest deployment caused login failures for multiple users.",
            },
            {
                "source": "logs",
                "type": "warning",
                "title": "High auth retry count detected",
                "content": "Multiple login retry attempts detected from clients after token expiry.",
            },
            {
                "source": "manual",
                "type": "note",
                "title": "Auth issue root cause",
                "content": "Root cause seems to be missing refresh-token fallback after deployment.",
            },
            {
                "source": "github",
                "type": "commit",
                "title": "Add tests for expired token login flow",
                "content": "Added test coverage for expired JWT login and refresh token fallback.",
            },
        ]

        for index, event in enumerate(sample_events):
            event["metadata"] = {"seeded": True}
            event["timestamp"] = now - timedelta(minutes=index * 9)
            event["embedding_status"] = EmbeddingStatus.not_required

        events = self._event_repository.create_events(sample_events)
        for event in events:
            relationship_service.detect_relationships_for_event(event)
        return events

    def clear_events(self) -> None:
        self._event_repository.clear_events()
        try:
            from app.services.embedding_index_service import embedding_index_service

            embedding_index_service.clear_index()
        except Exception:
            pass

    def _to_event_data(self, request: IngestEventRequest) -> dict[str, Any]:
        return {
            "source": request.source,
            "type": request.type,
            "title": request.title,
            "content": request.content,
            "metadata": request.metadata,
            "timestamp": request.timestamp or datetime.now(timezone.utc),
            "embedding_status": EmbeddingStatus.not_required,
        }
