from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    @abstractmethod
    def add_document(
        self,
        document_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete_all(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, str]:
        raise NotImplementedError
