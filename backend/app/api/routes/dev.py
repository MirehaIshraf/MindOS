from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import get_database_path
from app.services.event_service import EventService
from app.services.ingestion_service import IngestionService
from app.integrations.llm.fake_llm import FakeLLMClient
from app.integrations.llm.ollama_llm import OllamaLLMClient, OllamaLLMError
from app.services.chat_service import chat_service
from app.services.model_runtime_service import OLLAMA_FALLBACK_WARNING, model_runtime_service
from app.services.search_service import SearchService
from app.services.task_service import task_service
from app.services.relationship_service import relationship_service

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
    relationship_service.clear_relationships()
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


@router.post("/rebuild-relationships")
def rebuild_relationships() -> dict[str, object]:
    result = relationship_service.rebuild_relationships()
    return {
        "status": "rebuilt",
        "created": result["created"],
        "by_type": result["by_type"],
    }


@router.delete("/clear-relationships")
def clear_relationships() -> dict[str, str]:
    relationship_service.clear_relationships()
    return {
        "status": "cleared",
    }


@router.post("/test-llm")
def test_llm(payload: dict[str, str]) -> dict[str, object]:
    settings = get_settings()
    message = payload.get("message", "Say hello from MindOS")
    warning = None
    model = "fake-llm"

    if settings.enable_local_llm:
        try:
            if not model_runtime_service.is_model_available(settings.ollama_chat_model):
                raise OllamaLLMError("Ollama model is unavailable.")
            model = settings.ollama_chat_model
            reply = OllamaLLMClient().generate_response(
                message=message,
                history=[],
                context="No local memory context was requested for this model runtime test.",
                system_prompt="You are MindOS. Reply briefly and do not reveal hidden reasoning.",
            )
            return {"model": model, "reply": reply, "warning": warning}
        except (OllamaLLMError, RuntimeError):
            warning = OLLAMA_FALLBACK_WARNING

    if settings.enable_local_llm and warning is None:
        warning = OLLAMA_FALLBACK_WARNING

    reply = FakeLLMClient().generate_response(
        message=message,
        history=[],
        context=[{"title": "Model runtime test", "source": "mindos", "type": "debug", "content_preview": message}],
        system_prompt="You are MindOS. Reply briefly.",
    )
    return {"model": model, "reply": reply, "warning": warning}


@router.get("/state")
def dev_state() -> dict[str, object]:
    settings = get_settings()
    search_stats = search_service.get_search_stats()
    payload: dict[str, object] = {
        "storage": settings.storage_backend,
        "event_count": event_service.count_events(),
        "file_system_event_count": event_service.count_by_source().get("file_system", 0),
        "logs_event_count": event_service.count_by_source().get("logs", 0),
        "git_event_count": event_service.count_by_source().get("git", 0),
        "task_count": task_service.count_tasks(),
        "chat_session_count": chat_service.count_sessions(),
        "chat_message_count": chat_service.count_messages(),
        "relationship_count": relationship_service.count_relationships(),
        "relationships_by_type": relationship_service.count_by_type(),
        "events_by_source": event_service.count_by_source(),
        "events_by_category": search_stats.by_category,
        **model_runtime_service.get_status(),
    }
    if settings.storage_backend.lower() == "sqlite":
        payload["database_path"] = str(get_database_path())
    return payload
