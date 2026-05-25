from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.domain.models import Event
from app.services.memory_classifier import get_memory_category, is_hidden_from_default_memory


class ChromaVectorStore:
    def __init__(self) -> None:
        self._collection = None
        self._client = None

    def add_event(self, event: Event, embedding: list[float]) -> None:
        collection = self._get_collection()
        collection.upsert(
            ids=[event.id],
            embeddings=[embedding],
            documents=[event.title],
            metadatas=[self._metadata(event)],
        )

    def search_events(
        self,
        query_embedding: list[float],
        limit: int = 10,
        sources: list[str] | None = None,
        category: str | None = None,
        include_hidden: bool = True,
    ) -> list[dict[str, Any]]:
        collection = self._get_collection()
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=max(limit * 5, limit),
            include=["metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        source_set = {source.lower() for source in sources} if sources else None
        rows: list[dict[str, Any]] = []
        for event_id, metadata, distance in zip(ids, metadatas, distances):
            metadata = metadata or {}
            if source_set and str(metadata.get("source", "")).lower() not in source_set:
                continue
            if category and metadata.get("memory_category") != category:
                continue
            if bool(metadata.get("hidden_from_default")) and not include_hidden:
                continue
            rows.append(
                {
                    "event_id": event_id,
                    "distance": float(distance),
                    "score": 1 / (1 + float(distance)),
                    "metadata": metadata,
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def delete_event(self, event_id: str) -> None:
        self._get_collection().delete(ids=[event_id])

    def delete_all(self) -> None:
        client = self._get_client()
        try:
            client.delete_collection("mindos_events")
        except Exception:
            pass
        self._collection = None
        self._get_collection()

    def health_check(self) -> bool:
        try:
            self._get_collection()
            return True
        except Exception:
            return False

    def count(self) -> int:
        try:
            return int(self._get_collection().count())
        except Exception:
            return 0

    def _get_client(self):
        if self._client is None:
            try:
                import chromadb
            except Exception as exc:
                raise RuntimeError("ChromaDB is not available.") from exc

            settings = get_settings()
            path = Path(settings.chroma_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(path))
        return self._client

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._get_client().get_or_create_collection(name="mindos_events")
        return self._collection

    def _metadata(self, event: Event) -> dict[str, str | int | float | bool]:
        return {
            "event_id": event.id,
            "source": event.source.value,
            "type": event.type,
            "title": event.title,
            "memory_category": get_memory_category(event),
            "hidden_from_default": is_hidden_from_default_memory(event),
            "timestamp": event.timestamp.isoformat(),
        }


chroma_vector_store = ChromaVectorStore()
