from abc import ABC, abstractmethod

from app.domain.models import ChatSession, ChatStoredMessage, ConnectorSource, Event, ImportRun, Playbook, Relationship, TaskLog


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
    def count_by_embedding_status(self) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    def update_embedding_status(self, event_id: str, status: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_events_for_embedding(self, limit: int | None = None) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def update_event_policy(self, event_id: str, policy: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    def count_policy_eligibility(self) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    def clear_events(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_events_by_source(self, source: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete_events_by_ids(self, event_ids: list[str]) -> int:
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


class RelationshipRepository(ABC):
    @abstractmethod
    def create_relationship(
        self,
        from_event_id: str,
        to_event_id: str,
        relationship_type: str,
        strength: float,
        reason: str,
    ) -> Relationship:
        raise NotImplementedError

    @abstractmethod
    def list_relationships_for_event(self, event_id: str, limit: int = 10) -> list[Relationship]:
        raise NotImplementedError

    @abstractmethod
    def get_related_events(self, event_id: str, limit: int = 10) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def relationship_exists(self, from_event_id: str, to_event_id: str, relationship_type: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear_relationships(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_relationships_for_event_ids(self, event_ids: list[str]) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_relationships(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_by_type(self) -> dict[str, int]:
        raise NotImplementedError


class ConnectorSourceRepository(ABC):
    @abstractmethod
    def create_source(self, data: dict) -> ConnectorSource:
        raise NotImplementedError

    @abstractmethod
    def update_source(self, source_id: str, data: dict) -> ConnectorSource:
        raise NotImplementedError

    @abstractmethod
    def get_source(self, source_id: str) -> ConnectorSource | None:
        raise NotImplementedError

    @abstractmethod
    def list_sources(self, connector_type: str | None = None) -> list[ConnectorSource]:
        raise NotImplementedError

    @abstractmethod
    def delete_source(self, source_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def update_last_import(self, source_id: str, status: str, message: str, completed_at) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_import_run(self, data: dict) -> ImportRun:
        raise NotImplementedError

    @abstractmethod
    def list_import_runs(
        self,
        source_id: str | None = None,
        connector_type: str | None = None,
        limit: int = 20,
    ) -> list[ImportRun]:
        raise NotImplementedError

    @abstractmethod
    def count_sources(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_import_runs(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def clear_import_runs(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def clear_sources(self) -> int:
        raise NotImplementedError
