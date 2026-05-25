from fastapi import APIRouter, HTTPException, Query

from app.schemas.context import ContextBuildRequest, ContextPackage
from app.services.context_builder_service import context_builder_service

router = APIRouter(prefix="/context", tags=["context"])


@router.post("/build", response_model=ContextPackage)
def build_context(request: ContextBuildRequest) -> ContextPackage:
    if request.mode == "task":
        return context_builder_service.build_task_context(
            instruction=request.query,
            limit=request.limit,
            related_per_event=request.related_per_event,
        )
    return context_builder_service.build_chat_context(
        query=request.query,
        limit=request.limit,
        related_per_event=request.related_per_event,
    )


@router.get("/event/{event_id}", response_model=ContextPackage)
def get_event_context(event_id: str, related_limit: int = Query(default=10, ge=1, le=50)) -> ContextPackage:
    try:
        return context_builder_service.get_context_for_event(event_id, related_limit=related_limit)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Event not found.") from error
