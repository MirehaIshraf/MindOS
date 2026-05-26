from app.core.config import get_settings
from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus
from app.domain.models import Event
from app.integrations.embeddings.ollama_embedding_client import OllamaEmbeddingClient
from app.integrations.vector_store.chroma_vector_store import chroma_vector_store
from app.repositories.base import EventRepository
from app.services.embedding_text_service import build_event_embedding_text
from app.services.embedding_model_registry_service import embedding_model_registry_service


class EmbeddingIndexService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()
        self._embedding_client = OllamaEmbeddingClient()
        self._vector_store = chroma_vector_store

    def index_event(self, event: Event) -> dict:
        settings = get_settings()
        if not event.is_indexable:
            self._event_repository.update_embedding_status(event.id, EmbeddingStatus.not_required.value)
            return {"status": "skipped_not_indexable", "event_id": event.id, "reason": "not_indexable"}
        if not settings.enable_embeddings:
            self._event_repository.update_embedding_status(event.id, EmbeddingStatus.not_required.value)
            return {"status": "skipped", "event_id": event.id, "reason": "embeddings_disabled"}

        self._event_repository.update_embedding_status(event.id, EmbeddingStatus.pending.value)
        try:
            embedding_text = build_event_embedding_text(event)
            embedding = self._embedding_client.embed(embedding_text)
            self._vector_store.add_event(event, embedding)
            self._event_repository.update_embedding_status(event.id, EmbeddingStatus.indexed.value)
            return {"status": "indexed", "event_id": event.id}
        except Exception as exc:
            self._event_repository.update_embedding_status(event.id, EmbeddingStatus.failed.value)
            return {"status": "failed", "event_id": event.id, "error": str(exc)}

    def reindex_all(self) -> dict:
        if not get_settings().enable_embeddings:
            events = self._event_repository.list_events_for_embedding()
            for event in events:
                self._event_repository.update_embedding_status(event.id, EmbeddingStatus.not_required.value)
            return {
                "indexed": 0,
                "failed": 0,
                "skipped": len(events),
                "skipped_not_indexable": sum(1 for event in events if not event.is_indexable),
                "total": len(events),
                "errors": [],
            }
        try:
            self._vector_store.delete_all()
        except Exception as exc:
            return {
                "indexed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "errors": [{"error": f"ChromaDB unavailable: {exc}"}],
            }
        indexed = 0
        failed = 0
        skipped = 0
        skipped_not_indexable = 0
        errors: list[dict] = []
        events = self._event_repository.list_events_for_embedding()
        selected_model = embedding_model_registry_service.selected_model_name()
        embedding_model_registry_service.mark_index_model(selected_model, stale=True)
        for event in events:
            result = self.index_event(event)
            if result["status"] == "indexed":
                indexed += 1
            elif result["status"] == "skipped":
                skipped += 1
            elif result["status"] == "skipped_not_indexable":
                skipped_not_indexable += 1
                skipped += 1
            else:
                failed += 1
                errors.append({"event_id": event.id, "error": result.get("error", "unknown")})
        embedding_model_registry_service.mark_index_model(selected_model, stale=failed > 0)
        return {
            "indexed": indexed,
            "failed": failed,
            "skipped": skipped,
            "skipped_not_indexable": skipped_not_indexable,
            "total": len(events),
            "errors": errors[:20],
        }

    def clear_index(self) -> dict:
        try:
            self._vector_store.delete_all()
        except Exception:
            pass
        target_status = EmbeddingStatus.pending if get_settings().enable_embeddings else EmbeddingStatus.not_required
        events = self._event_repository.list_events_for_embedding()
        for event in events:
            status = EmbeddingStatus.not_required if not event.is_indexable else target_status
            self._event_repository.update_embedding_status(event.id, status.value)
        if get_settings().enable_embeddings:
            embedding_model_registry_service.mark_index_stale()
        return {"status": "cleared", "updated_events": len(events)}

    def get_embedding_status_summary(self) -> dict[str, int]:
        counts = {status.value: 0 for status in EmbeddingStatus}
        counts.update(self._event_repository.count_by_embedding_status())
        return counts

    def status(self, ollama_available: bool | None = None, ollama_models: set[str] | None = None) -> dict:
        settings = get_settings()
        embedding_settings = embedding_model_registry_service.get_settings_response(installed_models=ollama_models)
        selected_available = any(
            model.id == embedding_settings.selected_embedding_model_id and model.available
            for model in embedding_settings.models
        )
        return {
            "enabled": settings.enable_embeddings,
            "embedding_model": embedding_settings.selected_embedding_model,
            "selected_embedding_model": embedding_settings.selected_embedding_model,
            "selected_embedding_model_id": embedding_settings.selected_embedding_model_id,
            "index_model": embedding_settings.index_model_id,
            "index_stale": embedding_settings.index_stale,
            "embedding_model_available": selected_available,
            "ollama_available": self._embedding_client.health_check() if ollama_available is None else ollama_available,
            "chroma_available": self._vector_store.health_check(),
            "chroma_path": settings.chroma_path,
            "indexed_count": self._vector_store.count(),
            "event_status": self.get_embedding_status_summary(),
            **self._event_repository.count_policy_eligibility(),
        }

    def embeddings_available(self) -> bool:
        settings = get_settings()
        return settings.enable_embeddings and self._embedding_client.health_check() and self._vector_store.health_check()

    def index_stale_warning(self) -> str | None:
        if embedding_model_registry_service.index_stale():
            return "Embedding model changed. Reindex is required for best semantic search."
        return None

    def embed_query(self, query: str) -> list[float]:
        return self._embedding_client.embed(query)

    def semantic_search(
        self,
        query: str,
        limit: int,
        sources: list[str] | None,
        category: str | None,
        include_hidden: bool,
    ) -> list[dict]:
        embedding = self.embed_query(query)
        return self._vector_store.search_events(
            query_embedding=embedding,
            limit=limit,
            sources=sources,
            category=category,
            include_hidden=include_hidden,
        )


embedding_index_service = EmbeddingIndexService()
