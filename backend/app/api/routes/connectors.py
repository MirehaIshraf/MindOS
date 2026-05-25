from fastapi import APIRouter, HTTPException

from app.core.dependencies import get_event_repository, get_relationship_repository
from app.schemas.connectors import (
    ConnectorListResponse,
    FileImportRequest,
    FileImportResult,
    FilePreviewRequest,
    FilePreviewResult,
    GitImportRequest,
    GitImportResult,
    GitPreviewRequest,
    GitPreviewResult,
    LogImportRequest,
    LogImportResult,
    LogPreviewRequest,
    LogPreviewResult,
)
from app.services.connector_service import ConnectorService
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
    event_repository = get_event_repository()
    relationship_repository = get_relationship_repository()
    log_event_ids = [
        event.id
        for event in event_repository.list_all_events(include_hidden=True)
        if event.source.value == "logs"
    ]
    deleted_relationships = relationship_repository.delete_relationships_for_event_ids(log_event_ids)
    deleted_events = event_repository.delete_events_by_source("logs")
    return {
        "status": "cleared",
        "deleted_events": deleted_events,
        "deleted_relationships": deleted_relationships,
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
