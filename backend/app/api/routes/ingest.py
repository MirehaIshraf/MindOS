from fastapi import APIRouter, Body, HTTPException

from app.schemas.ingest import BulkIngestResponse, IngestEventRequest, IngestEventResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/ingest", tags=["ingest"])
service = IngestionService()


@router.post("", response_model=IngestEventResponse)
def ingest_event(request: IngestEventRequest) -> IngestEventResponse:
    event = service.ingest_event(request)
    return IngestEventResponse(event_id=event.id)


@router.post("/bulk", response_model=BulkIngestResponse)
def ingest_bulk(requests: list[IngestEventRequest] = Body(...)) -> BulkIngestResponse:
    if len(requests) > 50:
        raise HTTPException(status_code=400, detail="Bulk ingest accepts at most 50 events.")

    events = service.ingest_bulk(requests)
    return BulkIngestResponse(
        ingested=len(events),
        failed=0,
        event_ids=[event.id for event in events],
    )
