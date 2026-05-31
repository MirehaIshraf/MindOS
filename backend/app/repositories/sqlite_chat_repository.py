from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.core.database import ChatMessageRecord, ChatSessionRecord, get_session_factory, initialize_database
from app.domain.models import ChatSession, ChatStoredMessage
from app.repositories.base import ChatRepository
from app.repositories.sqlite_utils import dumps_json, loads_json


class SQLiteChatRepository(ChatRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

    def create_session(self, title: str | None = None) -> ChatSession:
        session_model = ChatSession(title=title or "New Chat")
        with self._session_factory() as session:
            session.add(
                ChatSessionRecord(
                    id=session_model.id,
                    title=session_model.title,
                    created_at=session_model.created_at,
                    updated_at=session_model.updated_at,
                )
            )
            session.commit()
        return session_model

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._session_factory() as session:
            record = session.get(ChatSessionRecord, session_id)
            return self._to_session(record) if record else None

    def list_sessions(self, limit: int = 20) -> list[ChatSession]:
        with self._session_factory() as session:
            records = session.scalars(select(ChatSessionRecord).order_by(ChatSessionRecord.updated_at.desc()).limit(limit)).all()
            return [self._to_session(record) for record in records]

    def add_message(self, session_id: str, role: str, content: str, metadata: dict | None = None) -> ChatStoredMessage:
        metadata = metadata or {}
        message = ChatStoredMessage(
            session_id=session_id,
            role=role,
            content=content,
            sources_used=metadata.get("sources_used", []),
            model=metadata.get("model"),
            provider=metadata.get("provider"),
            model_display_name=metadata.get("model_display_name"),
            search_mode=metadata.get("search_mode"),
            task_hint=metadata.get("task_hint"),
            context_summary=metadata.get("context_summary"),
            context_stats=metadata.get("context_stats"),
            warning=metadata.get("warning"),
            answer_style=metadata.get("answer_style"),
            intent=metadata.get("intent"),
        )
        with self._session_factory() as session:
            session_record = session.get(ChatSessionRecord, session_id)
            if session_record is None:
                raise KeyError(session_id)
            session.add(
                ChatMessageRecord(
                    id=message.id,
                    session_id=session_id,
                    role=role,
                    content=content,
                    metadata_json=dumps_json(metadata),
                    sources_used_json=dumps_json(message.sources_used),
                    model=message.model,
                    search_mode=message.search_mode,
                    task_hint=message.task_hint,
                    created_at=message.created_at,
                )
            )
            if role == "user" and session_record.title == "New Chat":
                session_record.title = content[:50] or "New Chat"
            session_record.updated_at = datetime.now(timezone.utc)
            session.commit()
        return message

    def list_messages(self, session_id: str) -> list[ChatStoredMessage]:
        with self._session_factory() as session:
            records = session.scalars(
                select(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id).order_by(ChatMessageRecord.created_at.asc())
            ).all()
            return [self._to_message(record) for record in records]

    def delete_session(self, session_id: str) -> bool:
        with self._session_factory() as session:
            record = session.get(ChatSessionRecord, session_id)
            if record is None:
                return False
            session.execute(delete(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id))
            session.delete(record)
            session.commit()
            return True

    def clear_sessions(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(ChatMessageRecord))
            session.execute(delete(ChatSessionRecord))
            session.commit()

    def count_sessions(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(ChatSessionRecord)) or 0)

    def count_messages(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(ChatMessageRecord)) or 0)

    def _to_session(self, record: ChatSessionRecord) -> ChatSession:
        return ChatSession(
            id=record.id,
            title=record.title,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _to_message(self, record: ChatMessageRecord) -> ChatStoredMessage:
        metadata = loads_json(record.metadata_json, {})
        return ChatStoredMessage(
            id=record.id,
            session_id=record.session_id,
            role=record.role,
            content=record.content,
            sources_used=loads_json(record.sources_used_json, []),
            model=record.model,
            provider=metadata.get("provider"),
            model_display_name=metadata.get("model_display_name"),
            search_mode=record.search_mode,
            task_hint=record.task_hint,
            context_summary=metadata.get("context_summary"),
            context_stats=metadata.get("context_stats"),
            warning=metadata.get("warning"),
            answer_style=metadata.get("answer_style"),
            intent=metadata.get("intent"),
            created_at=record.created_at,
        )
