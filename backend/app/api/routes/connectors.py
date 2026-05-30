from fastapi import APIRouter, HTTPException

from app.core.dependencies import get_event_repository, get_relationship_repository
from app.schemas.connectors import (
    ConnectorListResponse,
    ConnectorSourceCreateRequest,
    ConnectorSourceResponse,
    ConnectorSourcesResponse,
    ConnectorSourceUpdateRequest,
    FileImportRequest,
    FileImportResult,
    FilePreviewRequest,
    FilePreviewResult,
    GitImportRequest,
    GitImportResult,
    GitPreviewRequest,
    GitPreviewResult,
    ImportRunsResponse,
    LogImportRequest,
    LogImportResult,
    LogPreviewRequest,
    LogPreviewResult,
)
from app.schemas.ingest import CollectorClientsResponse
from app.services.connector_source_service import connector_source_service
from app.services.connector_service import ConnectorService
from app.services.external_ingest_service import external_ingest_service
from app.services.file_import_service import FileImportService
from app.services.git_import_service import GitImportService
from app.services.log_import_service import LogImportService

router = APIRouter(prefix="/connectors", tags=["connectors"])
service = ConnectorService()
file_import_service = FileImportService()
log_import_service = LogImportService()
git_import_service = GitImportService()


@router.get("", response_model=ConnectorListResponse)
def list_connectors() -> ConnectorListResponse:
    return service.list_connectors()


@router.get("/collectors", response_model=CollectorClientsResponse)
def list_collector_clients() -> CollectorClientsResponse:
    return CollectorClientsResponse(collectors=external_ingest_service.collector_clients())


@router.get("/sources", response_model=ConnectorSourcesResponse)
def list_connector_sources(connector_type: str | None = None) -> ConnectorSourcesResponse:
    return connector_source_service.list_sources(connector_type=connector_type)


@router.post("/sources", response_model=ConnectorSourceResponse)
def create_connector_source(request: ConnectorSourceCreateRequest) -> ConnectorSourceResponse:
    return connector_source_service.create_source(request)


@router.put("/sources/{source_id}", response_model=ConnectorSourceResponse)
def update_connector_source(source_id: str, request: ConnectorSourceUpdateRequest) -> ConnectorSourceResponse:
    try:
        return connector_source_service.update_source(source_id, request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Saved source not found.") from error


@router.delete("/sources/{source_id}")
def delete_connector_source(source_id: str) -> dict[str, str]:
    if not connector_source_service.delete_source(source_id):
        raise HTTPException(status_code=404, detail="Saved source not found.")
    return {"status": "deleted"}


@router.post("/sources/{source_id}/import")
def import_connector_source(source_id: str) -> dict[str, object]:
    try:
        return connector_source_service.run_source_import(source_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Saved source not found.") from error


@router.delete("/sources/{source_id}/events")
def clear_connector_source_events(source_id: str) -> dict[str, object]:
    try:
        return connector_source_service.clear_source_events(source_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Saved source not found.") from error


@router.get("/import-runs", response_model=ImportRunsResponse)
def list_import_runs(
    source_id: str | None = None,
    connector_type: str | None = None,
    limit: int = 20,
) -> ImportRunsResponse:
    return connector_source_service.list_import_runs(source_id=source_id, connector_type=connector_type, limit=limit)


@router.post("/file-system/preview", response_model=FilePreviewResult)
def preview_file_import(request: FilePreviewRequest) -> FilePreviewResult:
    try:
        return file_import_service.preview_folder(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/file-system/import", response_model=FileImportResult)
def import_files(request: FileImportRequest) -> FileImportResult:
    try:
        return file_import_service.import_folder(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/file-system/events")
def clear_file_system_events() -> dict[str, object]:
    return _clear_events_for_source("file_system")


@router.post("/logs/preview", response_model=LogPreviewResult)
def preview_log_import(request: LogPreviewRequest) -> LogPreviewResult:
    try:
        return log_import_service.preview_log(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/logs/import", response_model=LogImportResult)
def import_logs(request: LogImportRequest) -> LogImportResult:
    try:
        return log_import_service.import_log(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/logs/events")
def clear_log_events() -> dict[str, object]:
    return _clear_events_for_source("logs")


@router.delete("/git/events")
def clear_git_events() -> dict[str, object]:
    return _clear_events_for_source("git")


def _clear_events_for_source(source: str) -> dict[str, object]:
    event_repository = get_event_repository()
    relationship_repository = get_relationship_repository()
    event_ids = [
        event.id
        for event in event_repository.list_all_events(include_hidden=True)
        if event.source.value == source
    ]
    deleted_relationships = relationship_repository.delete_relationships_for_event_ids(event_ids)
    deleted_vectors = 0
    try:
        from app.integrations.vector_store.chroma_vector_store import chroma_vector_store

        for event_id in event_ids:
            chroma_vector_store.delete_event(event_id)
            deleted_vectors += 1
    except Exception:
        deleted_vectors = None
    deleted_events = event_repository.delete_events_by_source(source)
    return {
        "status": "cleared",
        "deleted_events": deleted_events,
        "deleted_relationships": deleted_relationships,
        "deleted_vectors": deleted_vectors,
    }


@router.post("/git/preview", response_model=GitPreviewResult)
def preview_git_import(request: GitPreviewRequest) -> GitPreviewResult:
    try:
        return git_import_service.preview_repo(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/git/import", response_model=GitImportResult)
def import_git_repo(request: GitImportRequest) -> GitImportResult:
    try:
        return git_import_service.import_repo(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
