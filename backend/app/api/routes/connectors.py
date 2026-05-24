from fastapi import APIRouter, HTTPException

from app.schemas.connectors import (
    ConnectorListResponse,
    FileImportRequest,
    FileImportResult,
    FilePreviewRequest,
    FilePreviewResult,
)
from app.services.connector_service import ConnectorService
from app.services.file_import_service import FileImportService

router = APIRouter(prefix="/connectors", tags=["connectors"])
service = ConnectorService()
file_import_service = FileImportService()


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
