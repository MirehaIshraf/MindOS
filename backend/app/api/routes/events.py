from fastapi import APIRouter, Body, HTTPException, Query

from app.schemas.events import EventResponse, RecentEventsResponse, RelatedEventItem, RelatedEventsResponse, RelationshipResponse
from app.services.event_service import EventService
from app.services.browser_memory_service import browser_memory_service
from app.services.relationship_service import relationship_service

router = APIRouter(prefix="/events", tags=["events"])
service = EventService()


@router.get("/recent", response_model=RecentEventsResponse)
def recent_events(
    source: str | None = None,
    category: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_hidden: bool = False,
) -> RecentEventsResponse:
    events = service.list_recent_events(source=source, category=category, limit=limit, offset=offset, include_hidden=include_hidden)
    total = service.count_filtered_events(source=source, category=category, include_hidden=include_hidden)
    return RecentEventsResponse(
        events=[service.to_event_response(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(events) < total,
    )


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str) -> EventResponse:
    event = service.get_event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return service.to_event_response(event)


@router.get("/{event_id}/related", response_model=RelatedEventsResponse)
def get_related_events(event_id: str, limit: int = Query(default=10, ge=1, le=50)) -> RelatedEventsResponse:
    event = service.get_event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    related = relationship_service.get_related_context(event_id, limit=limit)
    items = [
        RelatedEventItem(
            event=service.to_event_response(item["event"]),
            relationship=RelationshipResponse(**item["relationship"].model_dump()),
        )
        for item in related
    ]
    return RelatedEventsResponse(event_id=event_id, related=items, total=len(items))


@router.post("/{event_id}/summarize", response_model=EventResponse)
def summarize_event(event_id: str, payload: dict[str, str] = Body(default_factory=dict)) -> EventResponse:
    method = payload.get("method", "deterministic")
    try:
        event = browser_memory_service.summarize_browser_page(event_id, method=method)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return service.to_event_response(event)
