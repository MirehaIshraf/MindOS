from fastapi import APIRouter

from app.core.config import get_settings
from app.services.event_service import EventService
from app.services.chat_service import chat_service
from app.services.task_service import task_service

router = APIRouter(tags=["health"])
event_service = EventService()


@router.get("/health")
def health_check() -> dict[str, str | int]:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "storage": settings.storage_backend,
        "event_count": event_service.count_events(),
        "task_count": task_service.count_tasks(),
        "chat_session_count": chat_service.count_sessions(),
        "chat_message_count": chat_service.count_messages(),
        "search_mode": "keyword",
    }
