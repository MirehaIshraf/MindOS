from fastapi import APIRouter, HTTPException, Query

from app.schemas.events import EventResponse, RecentEventsResponse, RelatedEventItem, RelatedEventsResponse, RelationshipResponse
from app.services.event_service import EventService
from app.services.relationship_service import relationship_service

router = APIRouter(prefix="/events", tags=["events"])
service = EventService()


@router.get("/recent", response_model=RecentEventsResponse)
def recent_events(
    source: str | None = None,
    category: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    include_hidden: bool = False,
) -> RecentEventsResponse:
    events = service.list_recent_events(source=source, category=category, limit=limit, include_hidden=include_hidden)
    return RecentEventsResponse(events=[service.to_event_response(event) for event in events], total=len(events))


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
