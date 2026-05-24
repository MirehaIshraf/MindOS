from typing import Any

from app.integrations.vector_store.base import VectorStore


class MemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    def add_document(
        self,
        document_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._documents[document_id] = {
            "id": document_id,
            "text": text,
            "metadata": metadata or {},
        }

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        matches = [
            document
            for document in self._documents.values()
            if query.lower() in document["text"].lower()
        ]
        return matches[:limit]

    def delete_all(self) -> None:
        self._documents.clear()

    def health_check(self) -> dict[str, str]:
        return {
            "status": "ok",
            "backend": "memory",
        }
