from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import get_database_path
from app.services.event_service import EventService
from app.services.chat_service import chat_service
from app.services.model_runtime_service import model_runtime_service
from app.services.model_registry_service import model_registry_service
from app.services.embedding_index_service import embedding_index_service
from app.services.relationship_service import relationship_service
from app.services.task_service import task_service

router = APIRouter(tags=["health"])
event_service = EventService()


@router.get("/health")
def health_check() -> dict[str, str | int]:
    settings = get_settings()
    payload: dict[str, str | int] = {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "storage": settings.storage_backend,
        "event_count": event_service.count_events(),
        "task_count": task_service.count_tasks(),
        "chat_session_count": chat_service.count_sessions(),
        "chat_message_count": chat_service.count_messages(),
        "search_mode": "hybrid" if settings.enable_embeddings else "keyword",
    }
    if settings.storage_backend.lower() == "sqlite":
        payload["database_path"] = str(get_database_path())
    return payload


@router.get("/status")
def status() -> dict[str, object]:
    settings = get_settings()
    payload: dict[str, object] = {
        "backend": True,
        "storage": settings.storage_backend,
        "event_count": event_service.count_events(),
        "task_count": task_service.count_tasks(),
        "chat_session_count": chat_service.count_sessions(),
        "chat_message_count": chat_service.count_messages(),
        "relationship_count": relationship_service.count_relationships(),
        "search_mode": "keyword",
        "ollama_num_ctx": settings.ollama_num_ctx,
        "chat_context_direct_limit": settings.chat_context_direct_limit,
        "chat_context_related_per_event": settings.chat_context_related_per_event,
        "chat_context_max_total_chars": settings.chat_context_max_total_chars,
        "chat_history_limit": settings.chat_history_limit,
    }
    if settings.storage_backend.lower() == "sqlite":
        payload["database_path"] = str(get_database_path())
    payload.update(model_runtime_service.get_status())
    embedding_status = embedding_index_service.status()
    payload.update(
        {
            "embeddings_enabled": settings.enable_embeddings,
            "embedding_model": settings.ollama_embed_model,
            "chroma_available": embedding_status["chroma_available"],
            "chroma_indexed_count": embedding_status["indexed_count"],
            "semantic_search_default": settings.semantic_search_default,
            "search_mode": "hybrid" if settings.enable_embeddings else "keyword",
        }
    )
    chat_models_response = model_registry_service.get_chat_models_response()
    selected_model = next(
        (model for model in chat_models_response.models if model.id == chat_models_response.selected_chat_model),
        model_registry_service.fake_model(),
    )
    payload.update(
        {
            "selected_chat_model": chat_models_response.selected_chat_model,
            "available_chat_models_count": len(chat_models_response.models),
            "available_chat_models": [
                {
                    "id": model.id,
                    "display_name": model.display_name,
                    "provider": model.provider,
                    "type": model.type,
                    "available": model.available,
                }
                for model in chat_models_response.models
            ],
            "providers": model_registry_service.provider_status(),
            "active_provider": selected_model.provider if selected_model else "fake",
            "active_llm": selected_model.model_id if selected_model else "fake-llm",
            "model_warning": chat_models_response.warning,
        }
    )
    return payload
