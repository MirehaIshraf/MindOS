from datetime import datetime, timezone

from app.core.dependencies import get_chat_repository, get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.integrations.llm.fake_llm import FakeLLMClient
from app.repositories.base import ChatRepository, EventRepository
from app.schemas.chat import (
    ChatContextStats,
    ChatMessagesResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSessionsResponse,
    ChatSource,
    ChatStoredMessageResponse,
)
from app.schemas.context import ContextEvent, ContextPackage
from app.services.context_builder_service import ContextBuilderService
from app.services.relationship_service import relationship_service

SYSTEM_PROMPT = (
    "You are MindOS, a local-first AI assistant. You answer using the user's local memory when context is provided. "
    "Do not invent user data. If the context is insufficient, say so. For task requests, do not execute actions; "
    "only identify that it looks like a task."
)


class ChatService:
    def __init__(
        self,
        context_builder: ContextBuilderService | None = None,
        llm: FakeLLMClient | None = None,
        chat_repository: ChatRepository | None = None,
        event_repository: EventRepository | None = None,
    ) -> None:
        self._context_builder = context_builder or ContextBuilderService()
        self._llm = llm or FakeLLMClient()
        self._chat_repository = chat_repository or get_chat_repository()
        self._event_repository = event_repository or get_event_repository()

    def placeholder(self) -> dict[str, str]:
        return {
            "message": "Chat module is ready. Use POST /chat.",
        }

    def chat(self, request: ChatRequest) -> ChatResponse:
        session = self._chat_repository.get_session(request.session_id) if request.session_id else None
        if session is None:
            session = self._chat_repository.create_session(short_title(request.message))

        context_package: ContextPackage | None = None
        if request.use_context:
            context_package = self._context_builder.build_chat_context(
                query=request.message,
                limit=5,
                related_per_event=2,
                include_hidden=True,
            )

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
            context=context_package,
            system_prompt=SYSTEM_PROMPT,
        )
        task_hint = detect_task_hint(request.message)
        sources_used = context_sources(context_package)
        context_stats = context_stats_payload(context_package)
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
                "context_summary": context_package.summary if context_package else "",
                "context_stats": context_stats.model_dump() if context_stats else None,
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
            warning="; ".join(context_package.warnings) if context_package and context_package.warnings else None,
            context_summary=context_package.summary if context_package else "",
            context_stats=context_stats,
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
        event = self._event_repository.create_event(
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
        relationship_service.detect_relationships_for_event(event)

def context_sources(context_package: ContextPackage | None) -> list[ChatSource]:
    if context_package is None:
        return []
    return [
        *[context_event_to_source(event, "direct") for event in context_package.direct_events],
        *[context_event_to_source(event, "related") for event in context_package.related_events],
    ]


def context_event_to_source(event: ContextEvent, source_kind: str) -> ChatSource:
    return ChatSource(
        event_id=event.event_id,
        source=event.source,
        type=event.type,
        title=event.title,
        content_preview=event.content_preview,
        score=event.score or 0,
        match_reason=event.match_reason or "",
        timestamp=event.timestamp,
        source_kind=source_kind,
    )


def context_stats_payload(context_package: ContextPackage | None) -> ChatContextStats | None:
    if context_package is None:
        return None
    return ChatContextStats(
        direct_count=len(context_package.direct_events),
        related_count=len(context_package.related_events),
        relationship_count=len(context_package.relationships),
        sources=[group.source for group in context_package.source_groups],
        token_estimate=context_package.token_estimate,
    )


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
