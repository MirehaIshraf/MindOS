import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.tasks import (
    TaskCancelRequest,
    TaskConfirmRequest,
    TaskExecuteRequest,
    TaskHistoryResponse,
    TaskPlanningRequest,
    TaskPlanningResponse,
    TaskResponse,
)
from app.schemas.file_tasks import (
    FileSnapshotResponse,
    FileTaskExecuteRequest,
    FileTaskExecutionResult,
    FileTaskPlan,
    FileTaskPrepareRequest,
    FileTaskRecentResponse,
    FileTaskRecordResponse,
    FileTaskScanRequest,
    FileTaskUndoResult,
)
from app.services.file_task_execution_service import file_task_execution_service
from app.services.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


@router.get("")
def tasks_ready() -> dict[str, str]:
    return task_service.placeholder()


@router.post("/execute", response_model=TaskResponse)
def execute_task(request: TaskExecuteRequest) -> TaskResponse:
    try:
        return task_service.execute_task(request)
    except Exception as error:
        logger.exception("Failed to execute task")
        raise HTTPException(status_code=500, detail=f"Task execution failed: {error}") from error


@router.post("/plan", response_model=TaskPlanningResponse)
def plan_task(request: TaskPlanningRequest) -> TaskPlanningResponse:
    try:
        return task_service.plan_task(request)
    except Exception as error:
        logger.exception("Failed to plan task")
        raise HTTPException(status_code=500, detail=f"Task planning failed: {error}") from error


@router.post("/confirm", response_model=TaskResponse)
def confirm_task(request: TaskConfirmRequest) -> TaskResponse:
    return task_service.confirm_task(request)


@router.post("/cancel", response_model=TaskResponse)
def cancel_task(request: TaskCancelRequest) -> TaskResponse:
    try:
        return task_service.cancel_task(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/pending", response_model=TaskHistoryResponse)
def pending_tasks() -> TaskHistoryResponse:
    return task_service.list_pending()


@router.get("/history", response_model=TaskHistoryResponse)
def task_history(limit: int = Query(default=20, ge=1, le=100)) -> TaskHistoryResponse:
    return task_service.list_history(limit=limit)


@router.post("/file/scan", response_model=FileSnapshotResponse)
def scan_file_task(request: FileTaskScanRequest) -> FileSnapshotResponse:
    try:
        return file_task_execution_service.scan(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/file/prepare", response_model=FileTaskPlan)
def prepare_file_task(request: FileTaskPrepareRequest) -> FileTaskPlan:
    try:
        return file_task_execution_service.prepare(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/file/{task_id}/execute", response_model=FileTaskExecutionResult)
def execute_file_task(task_id: str, request: FileTaskExecuteRequest) -> FileTaskExecutionResult:
    try:
        return file_task_execution_service.execute(task_id, request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="File task not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/file/{task_id}/undo", response_model=FileTaskUndoResult)
def undo_file_task(task_id: str) -> FileTaskUndoResult:
    try:
        return file_task_execution_service.undo(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="File task not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/file/recent", response_model=FileTaskRecentResponse)
def recent_file_tasks(limit: int = Query(default=20, ge=1, le=100)) -> FileTaskRecentResponse:
    return file_task_execution_service.recent(limit=limit)


@router.get("/file/{task_id}", response_model=FileTaskRecordResponse)
def get_file_task(task_id: str) -> FileTaskRecordResponse:
    try:
        return file_task_execution_service.get(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="File task not found.") from error
