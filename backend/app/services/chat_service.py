import json
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.dependencies import get_chat_repository, get_chat_run_repository, get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.domain.models import ChatRun, ChatStoredMessage
from app.integrations.llm.base import LLMClient
from app.repositories.base import ChatRepository, ChatRunRepository, EventRepository
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
from app.services.conversation_context_service import ResolvedConversationContext, conversation_context_service
from app.services.model_registry_service import model_registry_service
from app.services.model_router_service import model_router_service
from app.services.query_intent_service import query_intent_service
from app.services.response_cleaner import clean_llm_response
from app.services.relationship_service import relationship_service
from app.services.mcp_tool_router_service import mcp_tool_router_service

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

FOLLOW_UP_PROMPT = """
The user is asking a follow-up question about the memory source discussed in the previous turn.
Use the provided primary source first.
If the source has a summary, use it.
If it has readable context excerpt, summarize only that captured content.
Include the source URL if available.
Do not say you lack access to memory if a source is provided.
If captured context is incomplete, say the summary is based on the captured excerpt.
"""


class ChatService:
    def __init__(
        self,
        context_builder: ContextBuilderService | None = None,
        llm: LLMClient | None = None,
        chat_repository: ChatRepository | None = None,
        chat_run_repository: ChatRunRepository | None = None,
        event_repository: EventRepository | None = None,
    ) -> None:
        self._context_builder = context_builder or ContextBuilderService()
        self._llm = llm
        self._chat_repository = chat_repository or get_chat_repository()
        self._chat_run_repository = chat_run_repository or get_chat_run_repository()
        self._event_repository = event_repository or get_event_repository()

    def placeholder(self) -> dict[str, str]:
        return {
            "message": "Chat module is ready. Use POST /chat.",
        }

    def chat(self, request: ChatRequest) -> ChatResponse:
        response, _ = self._run_chat_turn(request, record_user_message=True)
        return response

    def create_background_run(self, request: ChatRequest) -> ChatRun:
        session = self._chat_repository.get_session(request.session_id) if request.session_id else None
        if session is None:
            session = self._chat_repository.create_session(short_title(request.message))

        model_config = self._resolve_requested_model(request.model_id)
        self.mark_stale_runs_failed()
        active_run = self._chat_run_repository.get_active_run(session.id)
        if active_run is not None:
            raise ValueError("A chat response is already running for this session.")

        user_message = self._chat_repository.add_message(session.id, "user", request.message)
        self._record_chat_memory_event(
            event_type="chat_message",
            title=f"User asked MindOS about: {short_title(request.message)}",
            content=request.message,
            session_id=session.id,
            role="user",
        )
        return self._chat_run_repository.create_run(
            {
                "session_id": session.id,
                "user_message_id": user_message.id,
                "status": "queued",
                "user_message": request.message,
                "model_id": request.model_id,
                "provider": model_config.provider if model_config else None,
                "metadata_json": {"use_memory": request.use_context},
                "current_step": "queued",
                "progress_message": "Starting your request...",
                "progress_percent": 5,
                "progress_events": [
                    {
                        "step": "queued",
                        "message": "Starting your request...",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "level": "info",
                    }
                ],
            }
        )

    def process_background_run(self, run_id: str, request: ChatRequest) -> None:
        run = self._chat_run_repository.get_run(run_id)
        if run is None or run.status == "cancelled":
            return
        self._chat_run_repository.update_run(run_id, {"status": "running"})
        self._set_run_progress(run_id, "understanding", "Understanding your request...", 10)
        try:
            response, assistant_message = self._run_chat_turn(
                request,
                session_id=run.session_id,
                record_user_message=False,
                exclude_message_id=run.user_message_id,
                run_id=run_id,
            )
            latest_run = self._chat_run_repository.get_run(run_id)
            if latest_run and latest_run.metadata_json.get("cancellation_requested"):
                self._chat_run_repository.update_run(
                    run_id,
                    {
                        "status": "cancelled",
                        "completed_at": datetime.now(timezone.utc),
                        "assistant_message_id": assistant_message.id if assistant_message else None,
                        "result_json": response.model_dump(mode="json"),
                        "current_step": "cancelled",
                        "progress_message": "Response cancelled.",
                        "progress_percent": 100,
                    },
                )
                return
            self._set_run_progress(run_id, "completed", "Response ready.", 100)
            self._chat_run_repository.update_run(
                run_id,
                {
                    "status": "completed",
                    "assistant_message_id": assistant_message.id if assistant_message else None,
                    "resolved_query": response.resolved_query,
                    "provider": response.provider,
                    "completed_at": datetime.now(timezone.utc),
                    "result_json": response.model_dump(mode="json"),
                    "metadata_json": {
                        "answer_style": response.answer_style,
                        "intent": response.intent,
                        "is_follow_up": response.is_follow_up,
                    },
                },
            )
        except Exception as error:
            self._set_run_progress(run_id, "failed", "Something went wrong while preparing the response.", 100, level="error")
            self._chat_run_repository.update_run(
                run_id,
                {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc),
                    "error": str(error),
                },
            )

    def get_run(self, run_id: str) -> ChatRun | None:
        self.mark_stale_runs_failed()
        return self._chat_run_repository.get_run(run_id)

    def get_active_run(self, session_id: str) -> ChatRun | None:
        self.mark_stale_runs_failed()
        return self._chat_run_repository.get_active_run(session_id)

    def list_active_runs_debug(self) -> list[dict[str, object]]:
        self.mark_stale_runs_failed()
        now = datetime.now(timezone.utc)
        payload: list[dict[str, object]] = []
        for run in self._chat_run_repository.list_recent_runs(limit=100):
            if run.status not in {"queued", "running"}:
                continue
            age_seconds = max(0, int((now - ensure_aware(run.started_at)).total_seconds()))
            payload.append(
                {
                    "run_id": run.id,
                    "session_id": run.session_id,
                    "status": run.status,
                    "started_at": run.started_at,
                    "age_seconds": age_seconds,
                }
            )
        return payload

    def mark_stale_runs_failed(self, max_age_minutes: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        updated = 0
        for run in self._chat_run_repository.list_recent_runs(limit=100):
            if run.status not in {"queued", "running"}:
                continue
            if ensure_aware(run.started_at) >= cutoff:
                continue
            metadata = dict(run.metadata_json or {})
            metadata["stale"] = True
            self._chat_run_repository.update_run(
                run.id,
                {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc),
                    "error": "Chat run marked failed after exceeding the 30 minute active-run limit.",
                    "metadata_json": metadata,
                },
            )
            updated += 1
        return updated

    def cancel_run(self, run_id: str) -> ChatRun:
        return self._chat_run_repository.cancel_run(run_id)

    def clear_runs(self) -> None:
        self._chat_run_repository.clear_runs()

    def _set_run_progress(
        self,
        run_id: str | None,
        step: str,
        message: str,
        progress_percent: int | None = None,
        level: str = "info",
    ) -> None:
        if not run_id:
            return
        try:
            self._chat_run_repository.update_progress(run_id, step, message, progress_percent)
            self._chat_run_repository.append_progress_event(run_id, step, message, level=level)
        except KeyError:
            return

    def _run_chat_turn(
        self,
        request: ChatRequest,
        *,
        session_id: str | None = None,
        record_user_message: bool = True,
        exclude_message_id: str | None = None,
        run_id: str | None = None,
    ) -> tuple[ChatResponse, ChatStoredMessage | None]:
        session = self._chat_repository.get_session(session_id or request.session_id) if (session_id or request.session_id) else None
        if session is None:
            session = self._chat_repository.create_session(short_title(request.message))

        model_config = self._resolve_requested_model(request.model_id)
        recent_messages = self._chat_repository.list_messages(session.id)
        if exclude_message_id:
            recent_messages = [message for message in recent_messages if message.id != exclude_message_id]
        self._set_run_progress(run_id, "resolving_context", "Checking recent conversation context...", 18)
        conversation_context = conversation_context_service.resolve_follow_up(
            query=request.message,
            recent_messages=recent_messages,
        )
        self._set_run_progress(run_id, "understanding", "Checking whether local memory is needed...", 25)
        active_query = conversation_context.resolved_query if conversation_context.is_follow_up else request.message
        query_intent = query_intent_service.classify(request.message, conversation_context)
        context_profile = query_intent.retrieval_profile or (model_config.default_context_profile if model_config else "fast_chat")
        context_package: ContextPackage | None = None
        if context_profile != "no_memory" and (request.use_context or query_intent.needs_local_memory):
            self._set_run_progress(run_id, "retrieving_memory", "Searching local memory...", 35)
            context_package = self._context_builder.build_chat_context(
                query=active_query,
                profile=context_profile,
                include_hidden=True,
                intent=query_intent,
                source_event_ids=conversation_context.source_event_ids if conversation_context.is_follow_up else None,
            )
            context_package.metadata["conversation_context"] = conversation_context.model_dump()
            source_count = len(context_package.direct_events) + len(context_package.related_events)
            source_label = f"Reading {source_count} relevant source{'s' if source_count != 1 else ''}..." if source_count else "Checking retrieved context..."
            self._set_run_progress(run_id, "reading_sources", source_label, 55)
        else:
            self._set_run_progress(run_id, "general_chat", "Preparing a direct response...", 45)

        # Search happens before storage so the current user message cannot retrieve itself.
        if record_user_message:
            self._chat_repository.add_message(session.id, "user", request.message)
            self._record_chat_memory_event(
                event_type="chat_message",
                title=f"User asked MindOS about: {short_title(request.message)}",
                content=request.message,
                session_id=session.id,
                role="user",
            )

        # --- Check for pending MCP confirmation first ---
        # If user says "yes"/"proceed"/"confirm" and there are pending operations, execute them.
        confirmation_id = mcp_tool_router_service._is_confirmation_message(request.message)
        if confirmation_id:
            self._set_run_progress(run_id, "executing_confirmation", "Executing confirmed operations...", 70)
            try:
                exec_result = mcp_tool_router_service.execute_pending_confirmations(confirmation_id)
                if exec_result.get("success"):
                    # Format execution results for the LLM to summarize
                    results_text = json.dumps(exec_result.get("results", []), indent=2, default=str)
                    model_config = self._resolve_requested_model(request.model_id)
                    summary_messages = [
                        {"role": "system", "content": "You are MindOS. The user just confirmed file operations. Summarize what was done clearly and concisely."},
                        {"role": "user", "content": f"The following file operations were executed successfully:\n{results_text}\n\nPlease tell the user what was done."},
                    ]
                    summary_result = model_router_service.generate(
                        messages=summary_messages,
                        requested_model_id=request.model_id,
                        options={"temperature": 0.1},
                    )
                    mcp_result = {
                        "response": clean_llm_response(summary_result.reply),
                        "model_used": summary_result.model_used,
                        "provider": summary_result.provider,
                        "model_display_name": summary_result.model_display_name,
                        "tool_calls_made": exec_result.get("total_operations", 0),
                        "pending_confirmations": [],
                        "requires_confirmation": False,
                    }
                else:
                    mcp_result = {
                        "response": f"❌ Execution failed: {exec_result.get('error', 'Unknown error')}",
                        "model_used": "system",
                        "provider": "system",
                        "model_display_name": "System",
                        "tool_calls_made": 0,
                        "pending_confirmations": [],
                        "requires_confirmation": False,
                    }
            except Exception:
                mcp_result = {
                    "response": "❌ Failed to execute the confirmed operations. Please try again.",
                    "model_used": "system",
                    "provider": "system",
                    "model_display_name": "System",
                    "tool_calls_made": 0,
                    "pending_confirmations": [],
                    "requires_confirmation": False,
                }
        else:
            mcp_result = None

        # --- MCP tool-calling integration ---
        # If MCP tools are available and the query looks like a file-system command,
        # route it through the MCP tool router for LLM tool-calling.
        # Also auto-route when memory is off — there's nothing else to answer from.
        mcp_available = mcp_tool_router_service.has_mcp_tools_available()
        memory_is_off = context_profile == "no_memory" or not (request.use_context or query_intent.needs_local_memory)
        if mcp_result is None and mcp_available and (self._is_mcp_eligible(request.message) or memory_is_off):
            self._set_run_progress(run_id, "mcp_routing", "Routing to MCP tools...", 65)
            try:
                formatted_ctx = self._context_builder.format_context_for_llm(context_package) if context_package else ""
                mcp_result = mcp_tool_router_service.process_chat_with_mcp(
                    user_message=request.message,
                    context_text=formatted_ctx,
                    model_id=request.model_id,
                )
            except Exception:
                mcp_result = None  # Fall back to normal chat on MCP failure

        # Compute task_hint and answer_style regardless of MCP path (needed later)
        history = [message.model_dump(mode="json") for message in request.history]
        task_hint = detect_task_hint(request.message)
        answer_style = query_intent.answer_style or detect_answer_style(request.message, task_hint)

        if mcp_result is not None:
            reply = mcp_result["response"]
            model_name = mcp_result["model_used"]
            provider = mcp_result["provider"]
            model_display_name = mcp_result.get("model_display_name", model_name)
            llm_warning = None
            # If MCP returned pending confirmations, store them and append instructions to the reply
            if mcp_result.get("pending_confirmations"):
                confirmation_id = mcp_tool_router_service.store_pending_confirmations(mcp_result["pending_confirmations"])
                reply += f"\n\n---\n**⚠️ Confirmation Required:** The above file operations need your confirmation before execution. Reply **yes** or **proceed** to confirm, or **cancel** to abort."
        else:
            model_display = model_config.display_name if model_config else "selected model"
            self._set_run_progress(run_id, "generating", f"Preparing response with {model_display}...", 70)
            reply, model_name, provider, model_display_name, llm_warning = self._generate_reply(
                message=request.message,
                history=history,
                context_package=context_package,
                task_hint=task_hint,
                answer_style=answer_style,
                model_id=request.model_id,
                context_profile=context_profile,
                conversation_context=conversation_context,
                resolved_query=active_query,
                run_id=run_id,
                model_display_name=model_display,
            )
        self._set_run_progress(run_id, "finalizing", "Finalizing answer...", 92)
        reply = clean_llm_response(reply)
        sources_used = context_sources(context_package)
        context_stats = context_stats_payload(context_package)
        sources_payload = [source.model_dump(mode="json") for source in sources_used]
        response_context_metadata = conversation_context_service.build_response_metadata(
            intent=query_intent.intent,
            resolved_query=active_query,
            user_query=request.message,
            sources=sources_payload,
            conversation_context=conversation_context,
        )
        search_mode = (
            str(context_package.metadata.get("search_mode"))
            if context_package and context_package.metadata.get("search_mode")
            else ("hybrid" if get_settings().enable_embeddings else "keyword")
        )
        warning = combined_warning(
            "; ".join(context_package.warnings) if context_package and context_package.warnings else None,
            llm_warning,
        )

        assistant_message = self._chat_repository.add_message(
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
                "intent": query_intent.intent,
                **response_context_metadata,
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
                "intent": query_intent.intent,
                **response_context_metadata,
            },
        )

        return (
            ChatResponse(
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
                intent=query_intent.intent,
                is_follow_up=conversation_context.is_follow_up,
                resolved_query=active_query if active_query != request.message else None,
            ),
            assistant_message,
        )

    def resolve_context(self, session_id: str, query: str) -> ResolvedConversationContext:
        messages = self._chat_repository.list_messages(session_id)
        return conversation_context_service.resolve_follow_up(query=query, recent_messages=messages)

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
        self._chat_run_repository.clear_runs()

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
        if event.is_relationship_eligible:
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
        context_profile: str,
        conversation_context: ResolvedConversationContext | None = None,
        resolved_query: str | None = None,
        run_id: str | None = None,
        model_display_name: str | None = None,
    ) -> tuple[str, str, str, str, str | None]:
        system_prompt = prompt_for_answer_style(task_hint, answer_style)
        if conversation_context and conversation_context.is_follow_up:
            system_prompt += FOLLOW_UP_PROMPT
        if self._llm is not None:
            self._set_run_progress(run_id, "thinking", f"{model_display_name or getattr(self._llm, 'model', 'Selected model')} is thinking...", 80)
            return (
                self._llm.generate_response(message=message, history=history, context=context_package, system_prompt=system_prompt),
                getattr(self._llm, "model", "custom-llm"),
                "custom",
                getattr(self._llm, "model", "Custom LLM"),
                None,
            )

        settings = get_settings()
        formatted_context = self._context_builder.format_context_for_llm(context_package) if context_package else ""
        history_limit = 2 if context_profile == "speed_chat" else settings.chat_history_limit
        recent_history = [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in history[-history_limit:]
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        if conversation_context and conversation_context.recent_history:
            recent_history = conversation_context.recent_history[-min(4, history_limit or 4):]
        resolved_reference = ""
        if conversation_context and conversation_context.is_follow_up:
            resolved_reference = (
                "\n\nResolved reference:\n"
                f"{conversation_context.reason}\n"
                f"Primary source: {conversation_context.primary_source_title or conversation_context.primary_source_event_id}\n"
                f"URL: {conversation_context.primary_source_url or ''}\n"
                f"Entities: {', '.join(conversation_context.entities)}\n"
                f"Resolved query: {resolved_query or message}"
            )
        messages = [{"role": "system", "content": system_prompt}]
        if context_profile != "no_memory":
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Local memory context:\n\n"
                        + (formatted_context if formatted_context else "No local memory context was found for this request.")
                        + resolved_reference
                    ),
                }
            )
        messages.extend([*recent_history, {"role": "user", "content": f"/no_think\n\nUser question: {message}"}])
        self._set_run_progress(run_id, "thinking", f"{model_display_name or 'Selected model'} is thinking...", 80)
        result = model_router_service.generate(
            messages=messages,
            requested_model_id=model_id,
            options={"context_package": context_package},
        )
        return result.reply, result.model_used, result.provider, result.model_display_name, result.warning

    @staticmethod
    def _is_mcp_eligible(message: str) -> bool:
        """Check if a user message looks like it should be routed to MCP tools.

        Matches file-system related commands like:
        - "organize my Downloads folder"
        - "scan D:\\Projects"
        - "what files are in my folder"
        - "list of files in E:\\Demo"
        - "move PDFs to a separate folder"
        - "list file categories"
        - "folder summary"
        - "clean up my folder"
        - "show me what's in my configured folder"
        - "read the file xyz.txt"
        """
        import re as _re
        lower = message.lower()

        # Phrase-level matching (exact substrings)
        fs_phrases = [
            "organize folder", "organize my", "organize files",
            "scan folder", "scan my", "scan directory",
            "what files", "what's in", "whats in", "what is in",
            "list files", "list of files", "show files", "show me files",
            "folder summary", "folder structure",
            "move files", "move pdfs", "move images",
            "file categories", "file types", "list categories",
            "clean up folder", "clean up my", "cleanup folder",
            "sort files", "sort my files", "sort folder",
            "group files", "group by type",
            "file summary", "directory summary",
            "read the file", "read file", "open file",
            "file exists", "check file", "check if file",
            "show me what", "tell me what",
            "what's inside", "whats inside", "what is inside",
            "contents of", "content of",
            "in my folder", "in the folder",
            "list directory", "show directory",
        ]
        if any(kw in lower for kw in fs_phrases):
            return True

        # Email / Gmail intents (routed to the Gmail MCP tools)
        email_phrases = [
            "draft email", "draft mail", "draft an email", "draft a mail",
            "compose email", "compose mail", "compose an email",
            "send email", "send mail", "send an email", "send a mail",
            "write an email", "write email", "write a mail",
            "email to", "mail to", "create a draft", "create draft",
            "recent emails", "recent mail", "check my email", "check my inbox",
            "my inbox", "latest emails", "my emails", "my gmail",
        ]
        if any(kw in lower for kw in email_phrases):
            return True
        email_words = ["email", "emails", "mail", "inbox", "gmail"]
        email_actions = ["draft", "send", "compose", "write", "create", "check", "show", "list", "read", "recent"]
        has_email_word = any(f" {w} " in f" {lower} " or lower.startswith(w) or lower.endswith(w) for w in email_words)
        has_email_action = any(f" {w} " in f" {lower} " or lower.startswith(w) for w in email_actions)
        if has_email_word and has_email_action:
            return True

        # Word-level matching: check for combinations of file-related words
        file_words = ["file", "files", "folder", "directory", "directories"]
        action_words = ["list", "show", "scan", "find", "search", "check", "read", "open", "get", "see", "view", "browse", "explore", "organize", "sort", "clean", "move", "count"]
        has_file_word = any(f" {w} " in f" {lower} " or lower.startswith(w) or lower.endswith(w) for w in file_words)
        has_action_word = any(f" {w} " in f" {lower} " or lower.startswith(w) for w in action_words)
        if has_file_word and has_action_word:
            return True

        # Path pattern detection: messages containing Windows/Unix paths
        if _re.search(r'[A-Za-z]:[\\\/]', message) or _re.search(r'\/home\/|\/tmp\/|\/var\/', message):
            return True

        # "my files" / "my folder" pattern
        if "my files" in lower or "my folder" in lower or "my directory" in lower:
            return True

        return False

    def _resolve_requested_model(self, model_id: str | None):
        models = model_registry_service.list_chat_models()
        if model_id:
            model = next((item for item in models if item.id == model_id), None)
            if model:
                return model
        model, _ = model_registry_service.resolve_selected_chat_model(models)
        return model

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
    metadata = event.metadata or {}
    path = metadata.get("file_path") or metadata.get("path") or metadata.get("relative_path") or metadata.get("repo_path")
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
        metadata=metadata,
        url=metadata.get("url") if isinstance(metadata.get("url"), str) else None,
        path=path if isinstance(path, str) else None,
    )


def context_stats_payload(context_package: ContextPackage | None) -> ChatContextStats | None:
    if context_package is None:
        return None
    intent_payload = context_package.metadata.get("intent") if hasattr(context_package, "metadata") else None
    conversation_payload = context_package.metadata.get("conversation_context") if hasattr(context_package, "metadata") else None
    conversation_payload = conversation_payload if isinstance(conversation_payload, dict) else {}
    return ChatContextStats(
        direct_count=len(context_package.direct_events),
        related_count=len(context_package.related_events),
        relationship_count=len(context_package.relationships),
        sources=[group.source for group in context_package.source_groups],
        token_estimate=context_package.token_estimate,
        warnings=context_package.warnings,
        intent=intent_payload.get("intent") if isinstance(intent_payload, dict) else None,
        retrieval_profile=intent_payload.get("retrieval_profile") if isinstance(intent_payload, dict) else None,
        search_terms=intent_payload.get("search_terms", []) if isinstance(intent_payload, dict) else [],
        preferred_sources=intent_payload.get("preferred_sources", []) if isinstance(intent_payload, dict) else [],
        excluded_types=intent_payload.get("excluded_types", []) if isinstance(intent_payload, dict) else [],
        is_follow_up=bool(conversation_payload.get("is_follow_up")),
        resolved_query=conversation_payload.get("resolved_query") if isinstance(conversation_payload.get("resolved_query"), str) else None,
        primary_source_event_id=conversation_payload.get("primary_source_event_id") if isinstance(conversation_payload.get("primary_source_event_id"), str) else None,
        primary_source_title=conversation_payload.get("primary_source_title") if isinstance(conversation_payload.get("primary_source_title"), str) else None,
        primary_source_url=conversation_payload.get("primary_source_url") if isinstance(conversation_payload.get("primary_source_url"), str) else None,
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
    elif answer_style == "source_summary":
        prompt += """
The user is asking about a captured memory source. Use the provided captured source.
If a summary is ready, summarize it. If only an excerpt is available, summarize only the excerpt.
Include the URL when available.
Do not say you lack access to memory if a source is provided.
Do not treat this as root-cause analysis.
"""
    elif answer_style == "memory_lookup":
        prompt += """
The user is asking whether something exists in their local memory.
Answer directly.

If relevant memory is found:
- Start with "Yes" or "I found..."
- Name the exact memory item/page/file.
- Include URL/path if available.
- Keep answer concise.
- Do not speculate beyond the provided memory.

If no relevant memory is found:
- Say you could not find it in local memory.
- Suggest what source may need to be connected.

Do not give generic explanations.
"""
    elif answer_style == "conversational":
        prompt += "\nThe user is making a simple conversational turn. Reply briefly and naturally. Do not use local memory or root-cause formatting.\n"
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


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


chat_service = ChatService()
