from abc import ABC, abstractmethod


class BaseChatProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[dict[str, str]], model_id: str, options: dict | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        raise NotImplementedError
