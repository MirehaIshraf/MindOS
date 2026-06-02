from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.domain.models import ChatRun

from app.schemas.chat import (
    ChatMessagesResponse,
    ChatRequest,
    ChatRunCancelResponse,
    ChatRunCreateRequest,
    ChatRunStartResponse,
    ChatRunStatusResponse,
    ChatResolveContextRequest,
    ChatResolveContextResponse,
    ChatResponse,
    ChatSessionsResponse,
    ActiveChatRunResponse,
)
from app.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("")
def chat_ready() -> dict[str, str]:
    return chat_service.placeholder()


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return chat_service.chat(request)


@router.post("/runs", response_model=ChatRunStartResponse)
def create_chat_run(request: ChatRunCreateRequest, background_tasks: BackgroundTasks) -> ChatRunStartResponse:
    chat_request = ChatRequest(
        message=request.message,
        session_id=request.session_id,
        model_id=request.model_id,
        use_context=request.use_memory,
    )
    try:
        run = chat_service.create_background_run(chat_request)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    background_tasks.add_task(chat_service.process_background_run, run.id, chat_request)
    return ChatRunStartResponse(
        run_id=run.id,
        session_id=run.session_id,
        status="running",
        message="Chat response is running in the background.",
    )


@router.get("/runs/{run_id}", response_model=ChatRunStatusResponse)
def get_chat_run(run_id: str) -> ChatRunStatusResponse:
    run = chat_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Chat run not found.")
    return chat_run_response(run)


@router.post("/runs/{run_id}/cancel", response_model=ChatRunCancelResponse)
def cancel_chat_run(run_id: str) -> ChatRunCancelResponse:
    try:
        run = chat_service.cancel_run(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Chat run not found.") from error
    message = (
        "Chat run cancelled."
        if run.status == "cancelled"
        else "Cancellation requested. The current model call may finish first."
    )
    return ChatRunCancelResponse(run_id=run.id, status=run.status, message=message)


@router.get("/sessions/{session_id}/active-run", response_model=ActiveChatRunResponse)
def get_active_chat_run(session_id: str) -> ActiveChatRunResponse:
    run = chat_service.get_active_run(session_id)
    return ActiveChatRunResponse(active_run=chat_run_response(run) if run else None)


@router.get("/runs/debug/active")
def list_active_chat_runs_debug() -> dict[str, object]:
    runs = chat_service.list_active_runs_debug()
    return {
        "runs": runs,
        "total": len(runs),
    }


@router.post("/resolve-context", response_model=ChatResolveContextResponse)
def resolve_chat_context(request: ChatResolveContextRequest) -> ChatResolveContextResponse:
    resolved = chat_service.resolve_context(request.session_id, request.query)
    return ChatResolveContextResponse(**resolved.model_dump())


@router.get("/sessions", response_model=ChatSessionsResponse)
def list_chat_sessions(limit: int = 20) -> ChatSessionsResponse:
    return chat_service.list_sessions(limit=limit)


@router.get("/sessions/{session_id}/messages", response_model=ChatMessagesResponse)
def list_chat_messages(session_id: str) -> ChatMessagesResponse:
    return chat_service.list_messages(session_id)


@router.delete("/sessions/{session_id}")
def delete_chat_session(session_id: str) -> dict[str, str]:
    deleted = chat_service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return {"status": "deleted"}


@router.delete("/sessions")
def clear_chat_sessions() -> dict[str, str]:
    chat_service.clear_sessions()
    return {"status": "cleared"}


def chat_run_response(run: ChatRun) -> ChatRunStatusResponse:
    result = run.result_json if isinstance(run.result_json, dict) else None
    metadata = run.metadata_json or {}
    return ChatRunStatusResponse(
        run_id=run.id,
        session_id=run.session_id,
        status=run.status,
        user_message=run.user_message,
        assistant_message=result.get("reply") if result else None,
        result=result,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        user_message_id=run.user_message_id,
        assistant_message_id=run.assistant_message_id,
        model_id=run.model_id,
        provider=run.provider,
        answer_style=str(metadata.get("answer_style")) if metadata.get("answer_style") else None,
        intent=str(metadata.get("intent")) if metadata.get("intent") else None,
        metadata=metadata,
        current_step=run.current_step,
        progress_message=run.progress_message,
        progress_percent=run.progress_percent,
        progress_events=run.progress_events or [],
    )
