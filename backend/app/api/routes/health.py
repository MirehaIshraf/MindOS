from datetime import datetime, timezone
from uuid import uuid4

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
    warnings: list[str] = []
    payload: dict[str, object] = {
        "backend": True,
        "status_generated_at": datetime.now(timezone.utc).isoformat(),
        "status_request_id": uuid4().hex[:12],
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
    runtime_status: dict[str, object]
    try:
        runtime_status = model_runtime_service.get_status()
        payload.update(runtime_status)
    except Exception as error:
        warnings.append(f"Model runtime status unavailable: {error}")
        runtime_status = {
            "local_llm_enabled": settings.enable_local_llm,
            "ollama_available": False,
            "chat_model": settings.ollama_chat_model,
            "active_llm": "fake-llm",
            "ollama_models": [],
        }
        payload.update(runtime_status)
    ollama_models = set(runtime_status.get("ollama_models", []) or [])
    ollama_available = bool(runtime_status.get("ollama_available", False))
    try:
        embedding_status = embedding_index_service.status(ollama_available=ollama_available, ollama_models=ollama_models)
    except Exception as error:
        warnings.append(f"Embedding status unavailable: {error}")
        embedding_status = {
            "selected_embedding_model": settings.ollama_embed_model,
            "selected_embedding_model_id": "",
            "index_model": None,
            "index_stale": False,
            "embedding_model_available": False,
            "chroma_available": False,
            "indexed_count": 0,
        }
    payload.update(
        {
            "embeddings_enabled": settings.enable_embeddings,
            "embedding_model": embedding_status["selected_embedding_model"],
            "selected_embedding_model": embedding_status["selected_embedding_model"],
            "selected_embedding_model_id": embedding_status["selected_embedding_model_id"],
            "embedding_index_model": embedding_status["index_model"],
            "embedding_index_stale": embedding_status["index_stale"],
            "embedding_model_available": embedding_status["embedding_model_available"],
            "chroma_available": embedding_status["chroma_available"],
            "chroma_indexed_count": embedding_status["indexed_count"],
            "semantic_search_default": settings.semantic_search_default,
            "search_mode": "hybrid" if settings.enable_embeddings else "keyword",
        }
    )
    try:
        chat_models_response = model_registry_service.get_chat_models_response(ollama_models=ollama_models)
        discovered_ollama_models = sorted(ollama_models)
        providers = model_registry_service.provider_status(ollama_available=ollama_available)
        embedding_models_filtered_count = len(
            [
                model
                for model in discovered_ollama_models
                if any(marker in model.lower() for marker in ("embed", "embedding", "nomic-embed", "qwen3-embedding", "harrier"))
            ]
        )
        local_chat_models_count = max(len(discovered_ollama_models) - embedding_models_filtered_count, 0)
    except Exception as error:
        warnings.append(f"Model registry status unavailable: {error}")
        fake = model_registry_service.fake_model()
        chat_models_response = type(
            "ChatModelsStatusFallback",
            (),
            {"models": [fake], "selected_chat_model": fake.id, "warning": "Model registry unavailable. Using fallback."},
        )()
        discovered_ollama_models = []
        providers = {
            "ollama": {"configured": False, "enabled": True, "has_api_key": False, "available": False},
            "openai": {"configured": False, "enabled": False, "has_api_key": False, "available": None},
            "anthropic": {"configured": False, "enabled": False, "has_api_key": False, "available": None},
            "kimi": {"configured": False, "enabled": False, "has_api_key": False, "available": None},
        }
        local_chat_models_count = 0
        embedding_models_filtered_count = 0
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
            "providers": providers,
            "active_provider": selected_model.provider if selected_model else "fake",
            "active_llm": selected_model.model_id if selected_model else "fake-llm",
            "model_warning": chat_models_response.warning,
            "discovered_ollama_models": discovered_ollama_models,
            "local_chat_models_count": local_chat_models_count,
            "embedding_models_filtered_count": embedding_models_filtered_count,
            "status_warnings": warnings,
        }
    )
    return payload
