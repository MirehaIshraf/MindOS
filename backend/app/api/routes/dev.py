from fastapi import APIRouter, Body
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import get_database_path
from app.services.event_service import EventService
from app.services.ingestion_service import IngestionService
from app.services.chat_service import chat_service
from app.services.model_registry_service import model_registry_service
from app.services.model_router_service import model_router_service
from app.services.model_runtime_service import model_runtime_service
from app.services.search_service import SearchService
from app.services.task_service import task_service
from app.services.relationship_service import relationship_service
from app.services.embedding_index_service import embedding_index_service
from app.services.connector_source_service import connector_source_service
from app.services.memory_policy_service import get_memory_policy_for_event
from app.services.browser_memory_service import browser_memory_service

router = APIRouter(prefix="/dev", tags=["dev"])
ingestion_service = IngestionService()
event_service = EventService()
search_service = SearchService()


class ClearAllRequest(BaseModel):
    clear_saved_sources: bool = False
    clear_model_settings: bool = False


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


@router.post("/apply-memory-policy")
def apply_memory_policy() -> dict[str, object]:
    updated = 0
    for event in event_service._event_repository.list_all_events(include_hidden=True):
        policy = get_memory_policy_for_event(event.source.value, event.type, event.metadata)
        event_service._event_repository.update_event_policy(event.id, policy)
        updated += 1
    return {
        "status": "applied",
        "updated": updated,
        "counts": event_service._event_repository.count_policy_eligibility(),
    }


@router.post("/clean-memory-indexes")
def clean_memory_indexes() -> dict[str, object]:
    policy_result = apply_memory_policy()
    relationships = relationship_service.rebuild_relationships()
    embeddings = embedding_index_service.reindex_all() if get_settings().enable_embeddings else {"indexed": 0, "failed": 0, "skipped": 0, "skipped_not_indexable": 0, "total": 0}
    return {
        "status": "cleaned",
        "policy_updated": policy_result["updated"],
        "relationships_rebuilt": relationships["created"],
        "relationships_by_type": relationships["by_type"],
        "embeddings_reindexed": embeddings,
    }


@router.post("/dedupe-browser-pages")
def dedupe_browser_pages() -> dict[str, object]:
    return browser_memory_service.dedupe_browser_pages()


@router.post("/fix-browser-content-quality")
def fix_browser_content_quality() -> dict[str, object]:
    return browser_memory_service.fix_browser_content_quality()


@router.delete("/clear-all")
def clear_all(request: ClearAllRequest = Body(default_factory=ClearAllRequest)) -> dict[str, object]:
    options = request
    events_deleted = event_service.count_events()
    relationships_deleted = relationship_service.count_relationships()
    tasks_deleted = task_service.count_tasks()
    chats_deleted = chat_service.count_sessions()
    import_runs_deleted = connector_source_service.count_import_runs()
    saved_sources_deleted = 0
    warnings: list[str] = []

    relationship_service.clear_relationships()
    ingestion_service.clear_events()
    task_service.clear_tasks()
    chat_service.clear_sessions()
    import_runs_deleted = connector_source_service.clear_import_runs()

    vectors_deleted = None
    try:
        before = embedding_index_service.status().get("indexed_count", 0)
        embedding_index_service.clear_index()
        vectors_deleted = int(before) if isinstance(before, int) else None
    except Exception as error:
        warnings.append(f"Could not clear vector index: {error}")

    if options.clear_saved_sources:
        saved_sources_deleted = connector_source_service.clear_sources()

    model_settings_cleared = False
    if options.clear_model_settings:
        model_registry_service.clear_settings()
        model_settings_cleared = True

    return {
        "status": "cleared",
        "events_deleted": events_deleted,
        "relationships_deleted": relationships_deleted,
        "tasks_deleted": tasks_deleted,
        "chats_deleted": chats_deleted,
        "vectors_deleted": vectors_deleted,
        "import_runs_deleted": import_runs_deleted,
        "saved_sources_deleted": saved_sources_deleted,
        "model_settings_cleared": model_settings_cleared,
        "warnings": warnings,
    }


@router.post("/test-llm")
def test_llm(payload: dict[str, str]) -> dict[str, object]:
    message = payload.get("message", "Say hello from MindOS")
    result = model_router_service.generate(
        messages=[
            {"role": "system", "content": "You are MindOS. Reply briefly and do not reveal hidden reasoning."},
            {"role": "user", "content": message},
        ],
        requested_model_id=payload.get("model_id"),
        options={},
    )
    return {
        "model": result.model_used,
        "provider": result.provider,
        "model_display_name": result.model_display_name,
        "reply": result.reply,
        "warning": result.warning,
    }


@router.get("/state")
def dev_state() -> dict[str, object]:
    settings = get_settings()
    search_stats = search_service.get_search_stats()
    embedding_status = embedding_index_service.status()
    payload: dict[str, object] = {
        "storage": settings.storage_backend,
        "event_count": event_service.count_events(),
        "file_system_event_count": event_service.count_by_source().get("file_system", 0),
        "logs_event_count": event_service.count_by_source().get("logs", 0),
        "git_event_count": event_service.count_by_source().get("git", 0),
        "saved_sources_count": connector_source_service.count_sources(),
        "import_runs_count": connector_source_service.count_import_runs(),
        "task_count": task_service.count_tasks(),
        "chat_session_count": chat_service.count_sessions(),
        "chat_message_count": chat_service.count_messages(),
        "relationship_count": relationship_service.count_relationships(),
        "relationships_by_type": relationship_service.count_by_type(),
        "events_by_source": event_service.count_by_source(),
        "events_by_category": search_stats.by_category,
        "memory_policy": event_service._event_repository.count_policy_eligibility(),
        **model_runtime_service.get_status(),
        "selected_chat_model": model_registry_service.get_chat_models_response().selected_chat_model,
        "available_chat_models_count": len(model_registry_service.list_chat_models()),
        "providers": model_registry_service.provider_status(),
        "embeddings": embedding_status,
    }
    if settings.storage_backend.lower() == "sqlite":
        payload["database_path"] = str(get_database_path())
    return payload
