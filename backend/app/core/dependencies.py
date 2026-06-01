from app.core.config import get_settings
from app.repositories.base import ChatRepository, ConnectorSourceRepository, EventRepository, FileTaskRepository, PlaybookRepository, RelationshipRepository, TaskRepository
from app.repositories.memory_chat_repository import get_memory_chat_repository
from app.repositories.memory_connector_source_repository import get_memory_connector_source_repository
from app.repositories.memory_event_repository import get_memory_event_repository
from app.repositories.memory_file_task_repository import get_memory_file_task_repository
from app.repositories.memory_playbook_repository import get_memory_playbook_repository
from app.repositories.memory_relationship_repository import get_memory_relationship_repository
from app.repositories.memory_task_repository import get_memory_task_repository
from app.repositories.sqlite_chat_repository import SQLiteChatRepository
from app.repositories.sqlite_connector_source_repository import SQLiteConnectorSourceRepository
from app.repositories.sqlite_event_repository import SQLiteEventRepository
from app.repositories.sqlite_file_task_repository import SQLiteFileTaskRepository
from app.repositories.sqlite_playbook_repository import SQLitePlaybookRepository
from app.repositories.sqlite_relationship_repository import SQLiteRelationshipRepository
from app.repositories.sqlite_task_repository import SQLiteTaskRepository

_event_repository: EventRepository | None = None
_task_repository: TaskRepository | None = None
_file_task_repository: FileTaskRepository | None = None
_chat_repository: ChatRepository | None = None
_playbook_repository: PlaybookRepository | None = None
_relationship_repository: RelationshipRepository | None = None
_connector_source_repository: ConnectorSourceRepository | None = None


def use_sqlite() -> bool:
    return get_settings().storage_backend.lower() == "sqlite"


def get_event_repository() -> EventRepository:
    global _event_repository
    if _event_repository is None:
        _event_repository = SQLiteEventRepository() if use_sqlite() else get_memory_event_repository()
    return _event_repository


def get_task_repository() -> TaskRepository:
    global _task_repository
    if _task_repository is None:
        _task_repository = SQLiteTaskRepository() if use_sqlite() else get_memory_task_repository()
    return _task_repository


def get_file_task_repository() -> FileTaskRepository:
    global _file_task_repository
    if _file_task_repository is None:
        _file_task_repository = SQLiteFileTaskRepository() if use_sqlite() else get_memory_file_task_repository()
    return _file_task_repository


def get_chat_repository() -> ChatRepository:
    global _chat_repository
    if _chat_repository is None:
        _chat_repository = SQLiteChatRepository() if use_sqlite() else get_memory_chat_repository()
    return _chat_repository


def get_playbook_repository() -> PlaybookRepository:
    global _playbook_repository
    if _playbook_repository is None:
        _playbook_repository = SQLitePlaybookRepository() if use_sqlite() else get_memory_playbook_repository()
    return _playbook_repository


def get_relationship_repository() -> RelationshipRepository:
    global _relationship_repository
    if _relationship_repository is None:
        _relationship_repository = SQLiteRelationshipRepository(get_event_repository()) if use_sqlite() else get_memory_relationship_repository()
    return _relationship_repository


def get_connector_source_repository() -> ConnectorSourceRepository:
    global _connector_source_repository
    if _connector_source_repository is None:
        _connector_source_repository = SQLiteConnectorSourceRepository() if use_sqlite() else get_memory_connector_source_repository()
    return _connector_source_repository
