from fastapi import APIRouter, Body, HTTPException

from app.schemas.ingest import (
    BulkIngestResponse,
    ExternalBulkIngestRequest,
    ExternalBulkIngestResponse,
    ExternalEventIngestRequest,
    ExternalIngestResponse,
    ExternalIngestStatusResponse,
    IngestEventRequest,
    IngestEventResponse,
)
from app.services.external_ingest_service import PREFERRED_EXTERNAL_EVENT_TYPES, SUPPORTED_EXTERNAL_SOURCES, external_ingest_service
from app.services.connector_registry_service import connector_registry_service
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


@router.post(
    "/external",
    response_model=ExternalIngestResponse,
    summary="Ingest one event from an external local collector",
    description=(
        "Accepts local collector events from future clients such as the VSCode extension, "
        "browser extension, activity tracker, or local agent. Events are persisted to SQLite, "
        "memory policy is applied, and eligible events are indexed and related."
    ),
)
def ingest_external_event(request: ExternalEventIngestRequest) -> ExternalIngestResponse:
    try:
        return external_ingest_service.ingest_event(request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/external/bulk",
    response_model=ExternalBulkIngestResponse,
    summary="Bulk ingest external collector events",
    description="Ingests up to 100 external collector events. Each event is processed independently.",
)
def ingest_external_bulk(request: ExternalBulkIngestRequest) -> ExternalBulkIngestResponse:
    if len(request.events) > 100:
        raise HTTPException(status_code=400, detail="Bulk external ingest accepts at most 100 events.")
    event_ids: list[str] = []
    errors: list[dict] = []
    for index, event_request in enumerate(request.events):
        try:
            event = external_ingest_service.ingest_event_raw(event_request)
            event_ids.append(event.id)
        except PermissionError as exc:
            errors.append({"index": index, "source": event_request.source, "type": event_request.type, "error": str(exc), "status_code": 403})
        except Exception as exc:
            errors.append({"index": index, "source": event_request.source, "type": event_request.type, "error": str(exc)})
    failed = len(errors)
    return ExternalBulkIngestResponse(
        status="partial" if failed and event_ids else "failed" if failed else "ingested",
        ingested=len(event_ids),
        failed=failed,
        event_ids=event_ids,
        errors=errors,
    )


@router.get("/status", response_model=ExternalIngestStatusResponse)
def ingest_status() -> ExternalIngestStatusResponse:
    collectors = external_ingest_service.collector_clients()
    return ExternalIngestStatusResponse(
        external_ingest_enabled=True,
        supported_sources=SUPPORTED_EXTERNAL_SOURCES,
        preferred_event_types=PREFERRED_EXTERNAL_EVENT_TYPES,
        recent_external_events=external_ingest_service.recent_external_events_count(),
        collector_clients=collectors,
        connectors=connector_registry_service.list_connectors().connectors,
    )
