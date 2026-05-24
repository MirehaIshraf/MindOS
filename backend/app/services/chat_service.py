from datetime import datetime, timezone

from app.domain.enums import EmbeddingStatus, EventSource
from app.integrations.llm.fake_llm import FakeLLMClient
from app.repositories.memory_chat_repository import MemoryChatRepository, get_memory_chat_repository
from app.repositories.memory_event_repository import MemoryEventRepository, get_memory_event_repository
from app.schemas.chat import (
    ChatMessagesResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSessionsResponse,
    ChatSource,
    ChatStoredMessageResponse,
)
from app.services.search_service import SearchService

SYSTEM_PROMPT = (
    "You are MindOS, a local-first AI assistant. You answer using the user's local memory when context is provided. "
    "Do not invent user data. If the context is insufficient, say so. For task requests, do not execute actions; "
    "only identify that it looks like a task."
)


class ChatService:
    def __init__(
        self,
        search_service: SearchService | None = None,
        llm: FakeLLMClient | None = None,
        chat_repository: MemoryChatRepository | None = None,
        event_repository: MemoryEventRepository | None = None,
    ) -> None:
        self._search_service = search_service or SearchService()
        self._llm = llm or FakeLLMClient()
        self._chat_repository = chat_repository or get_memory_chat_repository()
        self._event_repository = event_repository or get_memory_event_repository()

    def placeholder(self) -> dict[str, str]:
        return {
            "message": "Chat module is ready. Use POST /chat.",
        }

    def chat(self, request: ChatRequest) -> ChatResponse:
        session = self._chat_repository.get_session(request.session_id) if request.session_id else None
        if session is None:
            session = self._chat_repository.create_session(short_title(request.message))

        search_response = None
        context: list[dict] = []
        if request.use_context:
            search_response = self._search_service.search_events(query=request.message, sources=None, limit=5)
            context = [search_result_to_context(result) for result in search_response.results]

        # Search happens before storage so the current user message cannot retrieve itself.
        self._chat_repository.add_message(session.id, "user", request.message)
        self._record_chat_memory_event(
            event_type="chat_message",
            title=f"User asked MindOS about: {short_title(request.message)}",
            content=request.message,
            session_id=session.id,
            role="user",
        )

        history = [message.model_dump(mode="json") for message in request.history]
        reply = self._llm.generate_response(
            message=request.message,
            history=history,
            context=context,
            system_prompt=SYSTEM_PROMPT,
        )
        task_hint = detect_task_hint(request.message)
        sources_used = [
            ChatSource(
                event_id=item["event_id"],
                source=item["source"],
                type=item["type"],
                title=item["title"],
                content_preview=item["content_preview"],
                score=item["score"],
                match_reason=item["match_reason"],
                timestamp=item["timestamp"],
            )
            for item in context
        ]
        sources_payload = [source.model_dump(mode="json") for source in sources_used]

        self._chat_repository.add_message(
            session.id,
            "assistant",
            reply,
            {
                "sources_used": sources_payload,
                "model": "fake-llm",
                "search_mode": "keyword",
                "task_hint": task_hint,
            },
        )
        self._record_chat_memory_event(
            event_type="chat_response",
            title=f"MindOS answered: {short_title(request.message)}",
            content=reply,
            session_id=session.id,
            role="assistant",
            metadata={
                "model": "fake-llm",
                "search_mode": "keyword",
                "sources_used_count": len(sources_used),
                "task_hint": task_hint,
            },
        )

        return ChatResponse(
            session_id=session.id,
            reply=reply,
            sources_used=sources_used,
            model="fake-llm",
            search_mode="keyword",
            task_hint=task_hint,
            warning=search_response.warning if search_response else None,
        )

    def list_sessions(self, limit: int = 20) -> ChatSessionsResponse:
        sessions = self._chat_repository.list_sessions(limit=limit)
        return ChatSessionsResponse(
            sessions=[ChatSessionResponse(**session.model_dump()) for session in sessions],
            total=len(sessions),
        )

    def list_messages(self, session_id: str) -> ChatMessagesResponse:
        messages = self._chat_repository.list_messages(session_id)
        return ChatMessagesResponse(
            messages=[ChatStoredMessageResponse(**message.model_dump()) for message in messages],
            total=len(messages),
        )

    def delete_session(self, session_id: str) -> bool:
        return self._chat_repository.delete_session(session_id)

    def clear_sessions(self) -> None:
        self._chat_repository.clear_sessions()

    def count_sessions(self) -> int:
        return self._chat_repository.count_sessions()

    def count_messages(self) -> int:
        return self._chat_repository.count_messages()

    def _record_chat_memory_event(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        session_id: str,
        role: str,
        metadata: dict | None = None,
    ) -> None:
        event_metadata = {
            "session_id": session_id,
            "message_role": role,
            "memory_category": "chat",
            "hidden_from_default": True,
        }
        if metadata:
            event_metadata.update(metadata)
        self._event_repository.create_event(
            {
                "source": EventSource.mindos,
                "type": event_type,
                "title": title,
                "content": content,
                "metadata": event_metadata,
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )


def search_result_to_context(result) -> dict:
    return {
        "event_id": result.event_id,
        "source": result.source,
        "type": result.type,
        "title": result.title,
        "content_preview": result.content_preview,
        "score": result.score,
        "match_reason": result.match_reason,
        "timestamp": result.timestamp.isoformat(),
    }


def short_title(value: str) -> str:
    title = " ".join(value.strip().split())
    return title[:50] or "New Chat"


def detect_task_hint(message: str) -> str | None:
    lower_message = message.lower()

    if ("jira" in lower_message or "ticket" in lower_message) and any(
        word in lower_message for word in ["create", "draft", "make"]
    ):
        return "create_jira_ticket"
    if "email" in lower_message and any(word in lower_message for word in ["send", "draft", "write"]):
        return "draft_email"
    if "pr" in lower_message or "pull request" in lower_message:
        return "create_pull_request"
    if "commit message" in lower_message or "commit" in lower_message:
        return "generate_commit_message"
    if "branch name" in lower_message or "branch" in lower_message:
        return "suggest_branch_name"
    if "weekly report" in lower_message or "report" in lower_message:
        return "weekly_report"
    return None


chat_service = ChatService()
