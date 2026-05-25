from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.dependencies import get_chat_repository, get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.integrations.llm.base import LLMClient
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
from app.services.model_router_service import model_router_service
from app.services.response_cleaner import clean_llm_response
from app.services.relationship_service import relationship_service

SYSTEM_PROMPT = """/no_think

Answer directly. Do not output hidden reasoning, thinking traces, scratchpad text, or chain-of-thought.

You are MindOS, a local-first AI assistant for a developer.

You answer using the user's local memory context provided by the backend.
The context may include files, logs, Git activity, tasks, chat history, and related memory.

Rules:
1. Use only the provided context when answering questions about the user's work.
2. If the context is insufficient, say what is missing.
3. Do not invent files, tickets, commits, logs, emails, or tasks.
4. Mention the most relevant sources naturally.
5. When related memory is provided, use it to connect events.
6. Keep answers clear, structured, and useful.
7. For task requests, do not claim that you executed anything. Only say that the task can be prepared safely and requires confirmation.
8. Do not reveal hidden reasoning or internal chain-of-thought.
9. Answer directly.

When the user asks about a failure, bug, error, incident, root cause, or why something happened, use this format:

## Root Cause
A concise explanation of the most likely cause.

## Evidence from Memory
- Source/type/title based evidence.
- Mention logs, commits, files, tasks, or chats only if present in context.

## Timeline
1. What happened first
2. What happened next
3. What fixed or relates to it

## Suggested Next Step
A practical next action.

## Sources Used
A short list of the most relevant memory items.

If context is insufficient, say:
"I don't have enough local memory to determine the root cause yet."
Then mention what data would help.
"""


class ChatService:
    def __init__(
        self,
        context_builder: ContextBuilderService | None = None,
        llm: LLMClient | None = None,
        chat_repository: ChatRepository | None = None,
        event_repository: EventRepository | None = None,
    ) -> None:
        self._context_builder = context_builder or ContextBuilderService()
        self._llm = llm
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
                profile="fast_chat",
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
        task_hint = detect_task_hint(request.message)
        answer_style = detect_answer_style(request.message, task_hint)
        reply, model_name, provider, model_display_name, llm_warning = self._generate_reply(
            message=request.message,
            history=history,
            context_package=context_package,
            task_hint=task_hint,
            answer_style=answer_style,
            model_id=request.model_id,
        )
        reply = clean_llm_response(reply)
        sources_used = context_sources(context_package)
        context_stats = context_stats_payload(context_package)
        sources_payload = [source.model_dump(mode="json") for source in sources_used]
        search_mode = "hybrid" if get_settings().enable_embeddings else "keyword"
        warning = combined_warning(
            "; ".join(context_package.warnings) if context_package and context_package.warnings else None,
            llm_warning,
        )

        self._chat_repository.add_message(
            session.id,
            "assistant",
            reply,
            {
                "sources_used": sources_payload,
                "model": model_name,
                "provider": provider,
                "model_display_name": model_display_name,
                "search_mode": search_mode,
                "task_hint": task_hint,
                "context_summary": context_package.summary if context_package else "",
                "context_stats": context_stats.model_dump() if context_stats else None,
                "warning": warning,
                "answer_style": answer_style,
            },
        )
        self._record_chat_memory_event(
            event_type="chat_response",
            title=f"MindOS answered: {short_title(request.message)}",
            content=reply,
            session_id=session.id,
            role="assistant",
            metadata={
                "model": model_name,
                "provider": provider,
                "model_display_name": model_display_name,
                "search_mode": search_mode,
                "sources_used_count": len(sources_used),
                "task_hint": task_hint,
                "warning": warning,
                "answer_style": answer_style,
            },
        )

        return ChatResponse(
            session_id=session.id,
            reply=reply,
            sources_used=sources_used,
            model=model_name,
            provider=provider,
            model_display_name=model_display_name,
            search_mode=search_mode,
            task_hint=task_hint,
            warning=warning,
            context_summary=context_package.summary if context_package else "",
            context_stats=context_stats,
            answer_style=answer_style,
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

    def _generate_reply(
        self,
        *,
        message: str,
        history: list[dict],
        context_package: ContextPackage | None,
        task_hint: str | None,
        answer_style: str,
        model_id: str | None,
    ) -> tuple[str, str, str, str, str | None]:
        system_prompt = prompt_for_answer_style(task_hint, answer_style)
        if self._llm is not None:
            return (
                self._llm.generate_response(message=message, history=history, context=context_package, system_prompt=system_prompt),
                getattr(self._llm, "model", "custom-llm"),
                "custom",
                getattr(self._llm, "model", "Custom LLM"),
                None,
            )

        settings = get_settings()
        formatted_context = self._context_builder.format_context_for_llm(context_package) if context_package else ""
        recent_history = [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in history[-settings.chat_history_limit :]
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Local memory context:\n\n"
                    + (formatted_context if formatted_context else "No local memory context was found for this request.")
                ),
            },
            *recent_history,
            {"role": "user", "content": f"/no_think\n\nUser question: {message}"},
        ]
        result = model_router_service.generate(
            messages=messages,
            requested_model_id=model_id,
            options={"context_package": context_package},
        )
        return result.reply, result.model_used, result.provider, result.model_display_name, result.warning

def context_sources(context_package: ContextPackage | None) -> list[ChatSource]:
    if context_package is None:
        return []
    return [
        *[context_event_to_source(event, "direct") for event in context_package.direct_events],
        *[context_event_to_source(event, "related") for event in context_package.related_events],
    ]


def context_event_to_source(event: ContextEvent, source_kind: str) -> ChatSource:
    relationship_type = None
    relationship_reason = None
    if source_kind == "related" and event.match_reason and ": " in event.match_reason:
        relationship_type, relationship_reason = event.match_reason.split(": ", 1)
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
        relationship_type=relationship_type,
        relationship_reason=relationship_reason,
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
        warnings=context_package.warnings,
    )


def combined_warning(*warnings: str | None) -> str | None:
    values = [warning for warning in warnings if warning]
    return "; ".join(values) if values else None


def prompt_for_answer_style(task_hint: str | None, answer_style: str) -> str:
    prompt = SYSTEM_PROMPT
    if answer_style == "root_cause":
        prompt += (
            "\nThe user is asking for root-cause analysis. Use the Root Cause / Evidence from Memory / "
            "Timeline / Suggested Next Step / Sources Used format. Be concise but structured.\n"
        )
    elif answer_style == "summary":
        prompt += "\nThe user is asking for a summary. Use a clean markdown summary with sections and bullets.\n"
    if task_hint:
        prompt += (
            "\nThe user's message looks like a task request of type: "
            + task_hint
            + ". Do not claim the task has been executed. Briefly explain that MindOS can prepare this safely "
            "and the user can confirm it in Tasks.\n"
        )
    return prompt


def short_title(value: str) -> str:
    title = " ".join(value.strip().split())
    return title[:50] or "New Chat"


def detect_task_hint(message: str) -> str | None:
    lower_message = message.lower()

    if ("jira" in lower_message or "ticket" in lower_message) and any(
        word in lower_message for word in ["create", "draft", "make", "prepare", "open"]
    ):
        return "create_jira_ticket"
    if "email" in lower_message and any(word in lower_message for word in ["send", "draft", "write", "prepare"]):
        return "draft_email"
    padded = f" {lower_message} "
    if "pull request" in lower_message or " create pr" in padded or " raise pr" in padded or " pr " in padded:
        return "create_pull_request"
    if "commit message" in lower_message or "generate commit" in lower_message:
        return "generate_commit_message"
    if "branch name" in lower_message or "suggest branch" in lower_message:
        return "suggest_branch_name"
    if "weekly report" in lower_message or "report" in lower_message:
        return "weekly_report"
    return None


def detect_answer_style(message: str, task_hint: str | None = None) -> str:
    if task_hint:
        return "task"
    text = message.lower()
    root_cause_terms = [
        "why",
        "root cause",
        "cause",
        "failed",
        "failure",
        "error",
        "exception",
        "bug",
        "issue",
        "problem",
        "incident",
        "broke",
        "not working",
    ]
    if any(term in text for term in root_cause_terms):
        return "root_cause"
    summary_terms = ["summarize", "summary", "overview", "what did i work on", "report"]
    if any(term in text for term in summary_terms):
        return "summary"
    return "normal"


chat_service = ChatService()
