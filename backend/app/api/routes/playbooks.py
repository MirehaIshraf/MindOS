import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.playbooks import (
    PlaybookCreateRequest,
    PlaybookListResponse,
    PlaybookResponse,
    PlaybookRunResponse,
    RecordStartResponse,
    RecordStopResponse,
)
from app.services.playbook_service import playbook_service

router = APIRouter(prefix="/playbooks", tags=["playbooks"])
logger = logging.getLogger(__name__)


@router.get("", response_model=PlaybookListResponse)
def list_playbooks() -> PlaybookListResponse:
    return playbook_service.list_playbooks()


@router.post("", response_model=PlaybookResponse)
def create_playbook(request: PlaybookCreateRequest) -> PlaybookResponse:
    try:
        return playbook_service.create_playbook(request)
    except Exception as error:
        logger.exception("Failed to create playbook")
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/status")
def recording_status() -> dict:
    return {"recording": playbook_service.is_recording()}


@router.get("/check")
def check_dependencies() -> dict:
    """Returns which PC-control dependencies are installed and ready."""
    from app.services import observation_service as obs
    return {
        "pynput_available": obs._PYNPUT_AVAILABLE,
        "pywinauto_available": obs._PYWINAUTO_AVAILABLE,
        "pillow_available": obs._PIL_AVAILABLE,
        "recording_active": obs.is_recording(),
    }


@router.post("/record/start", response_model=RecordStartResponse)
def start_recording() -> RecordStartResponse:
    try:
        return playbook_service.start_recording()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to start recording")
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/record/stop", response_model=RecordStopResponse)
def stop_recording() -> RecordStopResponse:
    try:
        return playbook_service.stop_recording()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to stop recording")
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/{playbook_id}", response_model=PlaybookResponse)
def get_playbook(playbook_id: str) -> PlaybookResponse:
    try:
        return playbook_service.get_playbook(playbook_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{playbook_id}")
def delete_playbook(playbook_id: str) -> dict:
    try:
        return playbook_service.delete_playbook(playbook_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{playbook_id}/run", response_model=PlaybookRunResponse)
def run_playbook(
    playbook_id: str,
    confirm_step: int | None = Query(default=None, description="Resume from this step index after user confirmation"),
) -> PlaybookRunResponse:
    try:
        return playbook_service.run_playbook(playbook_id, confirm_step=confirm_step)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        logger.exception("Playbook execution failed")
        raise HTTPException(status_code=500, detail=str(error)) from error
