from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import get_database_path
from app.services.event_service import EventService
from app.services.ingestion_service import IngestionService
from app.services.chat_service import chat_service
from app.services.search_service import SearchService
from app.services.task_service import task_service

router = APIRouter(prefix="/dev", tags=["dev"])
ingestion_service = IngestionService()
event_service = EventService()
search_service = SearchService()


@router.post("/sample-events")
def seed_sample_events() -> dict[str, object]:
    events = ingestion_service.seed_sample_events()
    return {
        "status": "seeded",
        "count": len(events),
        "event_ids": [event.id for event in events],
    }


@router.delete("/clear-events")
def clear_events() -> dict[str, str]:
    ingestion_service.clear_events()
    return {
        "status": "cleared",
    }


@router.delete("/clear-tasks")
def clear_tasks() -> dict[str, str]:
    task_service.clear_tasks()
    return {
        "status": "cleared",
    }


@router.delete("/clear-chats")
def clear_chats() -> dict[str, str]:
    chat_service.clear_sessions()
    return {
        "status": "cleared",
    }


@router.get("/state")
def dev_state() -> dict[str, object]:
    settings = get_settings()
    search_stats = search_service.get_search_stats()
    payload: dict[str, object] = {
        "storage": settings.storage_backend,
        "event_count": event_service.count_events(),
        "file_system_event_count": event_service.count_by_source().get("file_system", 0),
        "task_count": task_service.count_tasks(),
        "chat_session_count": chat_service.count_sessions(),
        "chat_message_count": chat_service.count_messages(),
        "events_by_source": event_service.count_by_source(),
        "events_by_category": search_stats.by_category,
    }
    if settings.storage_backend.lower() == "sqlite":
        payload["database_path"] = str(get_database_path())
    return payload
