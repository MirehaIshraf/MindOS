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
