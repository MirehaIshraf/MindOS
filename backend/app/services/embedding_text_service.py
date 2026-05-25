from app.core.config import get_settings
from app.domain.models import Event
from app.services.memory_classifier import get_memory_category

EMBEDDING_METADATA_KEYS = [
    "path",
    "file_path",
    "relative_path",
    "repo_name",
    "commit_hash",
    "task_type",
    "level",
]


def build_event_embedding_text(event: Event) -> str:
    settings = get_settings()
    metadata_lines = []
    for key in EMBEDDING_METADATA_KEYS:
        value = event.metadata.get(key)
        if value:
            metadata_lines.append(f"{key}: {value}")

    parts = [
        f"Title: {event.title}",
        f"Source: {event.source.value}",
        f"Type: {event.type}",
        f"Category: {get_memory_category(event)}",
        *metadata_lines,
        "Content:",
        event.content[: settings.embedding_text_max_chars],
    ]
    return "\n".join(part for part in parts if part)
