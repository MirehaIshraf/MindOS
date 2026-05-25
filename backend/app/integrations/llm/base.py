from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    @abstractmethod
    def generate_response(
        self,
        message: str,
        history: list[dict],
        context: Any,
        system_prompt: str | None = None,
    ) -> str:
        raise NotImplementedError
