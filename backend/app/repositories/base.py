from abc import ABC, abstractmethod

from app.domain.models import ChatSession, ChatStoredMessage, Event, Playbook, TaskLog


class EventRepository(ABC):
    @abstractmethod
    def create_event(self, event_data: dict) -> Event:
        raise NotImplementedError

    @abstractmethod
    def create_events(self, list_of_event_data: list[dict]) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def get_event_by_id(self, event_id: str) -> Event | None:
        raise NotImplementedError

    @abstractmethod
    def list_recent_events(
        self,
        source: str | None = None,
        category: str | None = None,
        limit: int = 20,
        include_hidden: bool = False,
    ) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def list_all_events(self, include_hidden: bool = True) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def count_events(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_by_source(self) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    def clear_events(self) -> None:
        raise NotImplementedError


class TaskRepository(ABC):
    @abstractmethod
    def create_task_log(
        self,
        task_type: str,
        instruction: str,
        status: str,
        preview: dict | None = None,
        result: dict | None = None,
        confirmation_token: str | None = None,
    ) -> TaskLog:
        raise NotImplementedError

    @abstractmethod
    def update_task_log(
        self,
        task_id: str,
        status: str | None = None,
        result: dict | None = None,
        confirmation_token: str | None = None,
        completed_at=None,
    ) -> TaskLog:
        raise NotImplementedError

    @abstractmethod
    def get_task_by_id(self, task_id: str) -> TaskLog | None:
        raise NotImplementedError

    @abstractmethod
    def list_recent_tasks(self, limit: int = 20) -> list[TaskLog]:
        raise NotImplementedError

    @abstractmethod
    def list_pending_tasks(self) -> list[TaskLog]:
        raise NotImplementedError

    @abstractmethod
    def cancel_task(self, task_id: str) -> TaskLog:
        raise NotImplementedError

    @abstractmethod
    def find_by_confirmation_token(self, token: str) -> TaskLog | None:
        raise NotImplementedError

    @abstractmethod
    def clear_tasks(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def count_tasks(self) -> int:
        raise NotImplementedError


class ChatRepository(ABC):
    @abstractmethod
    def create_session(self, title: str | None = None) -> ChatSession:
        raise NotImplementedError

    @abstractmethod
    def get_session(self, session_id: str) -> ChatSession | None:
        raise NotImplementedError

    @abstractmethod
    def list_sessions(self, limit: int = 20) -> list[ChatSession]:
        raise NotImplementedError

    @abstractmethod
    def add_message(self, session_id: str, role: str, content: str, metadata: dict | None = None) -> ChatStoredMessage:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, session_id: str) -> list[ChatStoredMessage]:
        raise NotImplementedError

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear_sessions(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def count_sessions(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_messages(self) -> int:
        raise NotImplementedError


class PlaybookRepository(ABC):
    @abstractmethod
    def add(self, playbook: Playbook) -> Playbook:
        raise NotImplementedError

    @abstractmethod
    def create(self, name: str, description: str = "", steps: list[str] | None = None) -> Playbook:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Playbook]:
        raise NotImplementedError

    @abstractmethod
    def get(self, playbook_id: str) -> Playbook | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, playbook_id: str, updates: dict) -> Playbook | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, playbook_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        raise NotImplementedError
