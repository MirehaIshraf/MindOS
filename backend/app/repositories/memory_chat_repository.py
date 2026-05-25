from datetime import datetime, timezone

from app.domain.models import ChatSession, ChatStoredMessage
from app.repositories.base import ChatRepository


class MemoryChatRepository(ChatRepository):
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._messages: dict[str, list[ChatStoredMessage]] = {}

    def create_session(self, title: str | None = None) -> ChatSession:
        session = ChatSession(title=title or "New Chat")
        self._sessions[session.id] = session
        self._messages[session.id] = []
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self, limit: int = 20) -> list[ChatSession]:
        sessions = sorted(self._sessions.values(), key=lambda session: session.updated_at, reverse=True)
        return sessions[:limit]

    def add_message(self, session_id: str, role: str, content: str, metadata: dict | None = None) -> ChatStoredMessage:
        session = self._sessions[session_id]
        metadata = metadata or {}
        message = ChatStoredMessage(
            session_id=session_id,
            role=role,
            content=content,
            sources_used=metadata.get("sources_used", []),
            model=metadata.get("model"),
            search_mode=metadata.get("search_mode"),
            task_hint=metadata.get("task_hint"),
            context_summary=metadata.get("context_summary"),
            context_stats=metadata.get("context_stats"),
            warning=metadata.get("warning"),
            answer_style=metadata.get("answer_style"),
        )
        self._messages.setdefault(session_id, []).append(message)
        title = session.title
        if role == "user" and title == "New Chat":
            title = content[:50] or "New Chat"
        self._sessions[session_id] = session.model_copy(update={"title": title, "updated_at": datetime.now(timezone.utc)})
        return message

    def list_messages(self, session_id: str) -> list[ChatStoredMessage]:
        return list(self._messages.get(session_id, []))

    def delete_session(self, session_id: str) -> bool:
        existed = session_id in self._sessions
        self._sessions.pop(session_id, None)
        self._messages.pop(session_id, None)
        return existed

    def clear_sessions(self) -> None:
        self._sessions.clear()
        self._messages.clear()

    def count_sessions(self) -> int:
        return len(self._sessions)

    def count_messages(self) -> int:
        return sum(len(messages) for messages in self._messages.values())


memory_chat_repository = MemoryChatRepository()


def get_memory_chat_repository() -> MemoryChatRepository:
    return memory_chat_repository
