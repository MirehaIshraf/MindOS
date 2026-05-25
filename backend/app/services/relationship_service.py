import re
from datetime import timezone

from app.core.dependencies import get_event_repository, get_relationship_repository
from app.domain.models import Event, Relationship
from app.repositories.base import EventRepository, RelationshipRepository

STOP_WORDS = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "in",
    "and",
    "or",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "after",
    "before",
    "will",
    "was",
    "were",
    "has",
    "have",
    "been",
}
FIX_WORDS = {"fix", "fixed", "resolve", "resolved", "patch", "handled", "updated"}
ISSUE_WORDS = {"error", "bug", "failure", "failed", "issue", "exception", "warning"}
IDENTIFIER_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b|\b[0-9a-f]{7,40}\b")


class RelationshipService:
    def __init__(
        self,
        event_repository: EventRepository | None = None,
        relationship_repository: RelationshipRepository | None = None,
    ) -> None:
        self._event_repository = event_repository or get_event_repository()
        self._relationship_repository = relationship_repository or get_relationship_repository()

    def detect_relationships_for_event(self, event: Event) -> list[Relationship]:
        created: list[Relationship] = []
        topic_candidates: list[tuple[float, Event, str]] = []
        temporal_candidates: list[Event] = []

        for other in self._event_repository.list_all_events(include_hidden=True):
            if other.id == event.id:
                continue

            created.extend(self._structured_relationships(event, other))

            mention = self._mention_relationship(event, other)
            if mention:
                created.append(mention)

            shared_tokens = self._shared_tokens(event, other)
            if len(shared_tokens) >= 3:
                strength = min(0.7, 0.4 + len(shared_tokens) * 0.05)
                topic_candidates.append((strength, other, f"Events share topic keywords: {', '.join(shared_tokens[:5])}"))

            if self._within_minutes(event, other, 30) and shared_tokens:
                temporal_candidates.append(other)

            fix = self._fix_relationship(event, other, shared_tokens)
            if fix:
                created.append(fix)

        topic_candidates.sort(key=lambda item: item[0], reverse=True)
        for strength, other, reason in topic_candidates[:5]:
            created.append(self._create(event.id, other.id, "SAME_TOPIC", strength, reason))

        for other in temporal_candidates[:5]:
            created.append(self._create(event.id, other.id, "TEMPORAL_NEARBY", 0.4, "Events occurred close together and share context"))

        return [relationship for relationship in created if relationship is not None]

    def rebuild_relationships(self) -> dict:
        self._relationship_repository.clear_relationships()
        for event in self._event_repository.list_all_events(include_hidden=True):
            self.detect_relationships_for_event(event)
        return {"created": self._relationship_repository.count_relationships(), "by_type": self._relationship_repository.count_by_type()}

    def get_related_context(self, event_id: str, limit: int = 5) -> list[dict]:
        return self._relationship_repository.get_related_events(event_id, limit=limit)

    def clear_relationships(self) -> None:
        self._relationship_repository.clear_relationships()

    def count_relationships(self) -> int:
        return self._relationship_repository.count_relationships()

    def count_by_type(self) -> dict[str, int]:
        return self._relationship_repository.count_by_type()

    def related_count(self, event_id: str) -> int:
        return len(self._relationship_repository.list_relationships_for_event(event_id, limit=1000))

    def _structured_relationships(self, event: Event, other: Event) -> list[Relationship]:
        relationships: list[Relationship] = []
        if self._shared_metadata_value(event, other, ["path", "file_path", "relative_path", "name"]):
            relationships.append(self._create(event.id, other.id, "SAME_FILE", 0.85, "Events reference the same file"))
        if self._shared_metadata_value(event, other, ["repo", "repo_name", "repo_path"]):
            relationships.append(self._create(event.id, other.id, "SAME_REPO", 0.75, "Events reference the same repository"))
        if self._shared_metadata_value(event, other, ["task_id"]):
            relationships.append(self._create(event.id, other.id, "SAME_TASK", 0.95, "Events belong to the same task lifecycle"))
        return [relationship for relationship in relationships if relationship is not None]

    def _mention_relationship(self, event: Event, other: Event) -> Relationship | None:
        haystack = f"{event.title} {event.content}".lower()
        identifiers = set(IDENTIFIER_RE.findall(f"{other.title} {other.content}"))
        for key in ["task_id", "commit_hash", "short_hash", "name"]:
            value = other.metadata.get(key)
            if isinstance(value, str):
                identifiers.add(value)
        for identifier in identifiers:
            if identifier and identifier.lower() in haystack:
                return self._create(event.id, other.id, "MENTIONS", 0.9, "One event explicitly mentions another event identifier")
        return None

    def _fix_relationship(self, event: Event, other: Event, shared_tokens: list[str]) -> Relationship | None:
        event_text = self._text(event)
        other_text = self._text(other)
        event_is_fix = any(word in event_text for word in FIX_WORDS)
        other_is_fix = any(word in other_text for word in FIX_WORDS)
        event_is_issue = any(word in event_text for word in ISSUE_WORDS)
        other_is_issue = any(word in other_text for word in ISSUE_WORDS)
        if not shared_tokens:
            return None
        event_time = event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
        other_time = other.timestamp if other.timestamp.tzinfo else other.timestamp.replace(tzinfo=timezone.utc)
        if event_is_issue and other_is_fix and other_time >= event_time:
            return self._create(event.id, other.id, "FIXED_BY", 0.8, "A later event appears to fix an earlier issue")
        if other_is_issue and event_is_fix and event_time >= other_time:
            return self._create(other.id, event.id, "FIXED_BY", 0.8, "A later event appears to fix an earlier issue")
        return None

    def _create(self, from_event_id: str, to_event_id: str, relationship_type: str, strength: float, reason: str) -> Relationship | None:
        if from_event_id == to_event_id:
            return None
        if self._relationship_repository.relationship_exists(from_event_id, to_event_id, relationship_type):
            return None
        return self._relationship_repository.create_relationship(from_event_id, to_event_id, relationship_type, strength, reason)

    def _shared_metadata_value(self, event: Event, other: Event, keys: list[str]) -> bool:
        for key in keys:
            left = event.metadata.get(key)
            right = other.metadata.get(key)
            if left and right and left == right:
                return True
        return False

    def _tokens(self, event: Event) -> set[str]:
        text = f"{event.title} {event.content[:1000]}".lower()
        return {token for token in re.findall(r"[a-z0-9_]{3,}", text) if token not in STOP_WORDS}

    def _shared_tokens(self, event: Event, other: Event) -> list[str]:
        return sorted(self._tokens(event).intersection(self._tokens(other)))

    def _within_minutes(self, event: Event, other: Event, minutes: int) -> bool:
        left = event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
        right = other.timestamp if other.timestamp.tzinfo else other.timestamp.replace(tzinfo=timezone.utc)
        return abs((left - right).total_seconds()) <= minutes * 60

    def _text(self, event: Event) -> str:
        return f"{event.title} {event.content[:1000]} {event.type}".lower()


relationship_service = RelationshipService()
