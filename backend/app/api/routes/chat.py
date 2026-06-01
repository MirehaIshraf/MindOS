from fastapi import APIRouter, HTTPException

from app.schemas.chat import (
    ChatMessagesResponse,
    ChatRequest,
    ChatResolveContextRequest,
    ChatResolveContextResponse,
    ChatResponse,
    ChatSessionsResponse,
)
from app.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("")
def chat_ready() -> dict[str, str]:
    return chat_service.placeholder()


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return chat_service.chat(request)


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
