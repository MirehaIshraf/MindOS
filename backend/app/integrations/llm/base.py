from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def generate_response(
        self,
        message: str,
        history: list[dict],
        context: list[dict],
        system_prompt: str | None = None,
    ) -> str:
        raise NotImplementedError
