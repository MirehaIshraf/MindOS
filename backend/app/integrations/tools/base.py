from abc import ABC, abstractmethod
from typing import Any

from app.domain.enums import PermissionLevel


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def permission_level(self) -> PermissionLevel:
        raise NotImplementedError

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
