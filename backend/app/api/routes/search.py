from fastapi import APIRouter, HTTPException

from app.schemas.events import EventResponse
from app.schemas.search import SearchRequest, SearchResponse, SearchStatsResponse
from app.services.event_service import EventService
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])
service = SearchService()
event_service = EventService()


@router.post("", response_model=SearchResponse)
def search_events(request: SearchRequest) -> SearchResponse:
    return service.search_events(
        query=request.query,
        sources=request.sources,
        category=request.category,
        limit=request.limit,
        include_hidden=request.include_hidden,
        search_mode=request.search_mode,
        context_only=request.context_only,
    )


@router.get("/stats", response_model=SearchStatsResponse)
def search_stats() -> SearchStatsResponse:
    return service.get_search_stats()


@router.get("/event/{event_id}", response_model=EventResponse)
def search_event_detail(event_id: str) -> EventResponse:
    event = service.get_event_detail(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event_service.to_event_response(event)
