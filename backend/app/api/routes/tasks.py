import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.tasks import (
    TaskCancelRequest,
    TaskConfirmRequest,
    TaskHistoryClearResponse,
    TaskExecuteRequest,
    TaskHistoryResponse,
    TaskPlanningRequest,
    TaskPlanningResponse,
    TaskResponse,
)
from app.schemas.task_actions import ActionCapabilityRegistry, TaskActionExecuteRequest, TaskActionExecuteResponse, TaskIntentPrepareRequest, TaskIntentPrepareResponse
from app.schemas.file_tasks import (
    DocumentSummaryCompleteRequest,
    DocumentSummaryCompleteResponse,
    DocumentSummaryPrepareRequest,
    DocumentSummaryPrepareResponse,
    FileSnapshotResponse,
    GeneratedSummarySaveRequest,
    GeneratedSummarySaveResponse,
    IndexedDocumentSummaryPrepareRequest,
    LogAnalysisPrepareRequest,
    LogAnalysisPrepareResponse,
    LogAnalysisSaveRequest,
    FileTaskExecuteRequest,
    FileTaskExecutionResult,
    FileTaskLlmPlanRequest,
    FileTaskPlan,
    FileTaskPrepareRequest,
    FileTaskRecentResponse,
    FileTaskRecordResponse,
    FileTaskScanRequest,
    FileTaskUndoResult,
)
from app.schemas.file_index import IndexedFileSearchRequest, IndexedFileSearchResponse, ResolveIndexedAttachmentsRequest, ResolveIndexedAttachmentsResponse
from app.schemas.gmail import GmailDraftPrepareRequest, GmailDraftPrepareResponse
from app.schemas.jira import JiraIssueDraftRequest, JiraIssueDraftResponse
from app.services.document_summary_task_service import document_summary_task_service
from app.services.file_index_service import file_index_service
from app.services.file_task_execution_service import file_task_execution_service
from app.services.file_task_llm_planner_service import file_task_llm_planner_service
from app.services.file_task_planner_service import file_task_planner_service
from app.services.file_snapshot_service import file_snapshot_service
from app.services.gmail_draft_planner import gmail_draft_planner
from app.services.jira_issue_planner_service import jira_issue_planner_service
from app.services.log_analysis_task_service import log_analysis_task_service
from app.services.task_action_execution_service import TaskActionExecutionError, task_action_execution_service
from app.services.task_intent_planner_service import task_intent_planner_service
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


@router.post("/prepare", response_model=TaskIntentPrepareResponse)
def prepare_task_intent(request: TaskIntentPrepareRequest) -> TaskIntentPrepareResponse:
    try:
        return task_intent_planner_service.prepare(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare task intent")
        raise HTTPException(status_code=500, detail=f"Task preparation failed: {error}") from error


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


@router.delete("/history", response_model=TaskHistoryClearResponse)
def clear_task_history() -> TaskHistoryClearResponse:
    return TaskHistoryClearResponse(deleted_count=task_service.clear_tasks())


@router.get("/actions/capabilities", response_model=ActionCapabilityRegistry)
def task_action_capabilities() -> ActionCapabilityRegistry:
    return task_action_execution_service.capabilities()


@router.post("/actions/execute", response_model=TaskActionExecuteResponse)
def execute_task_action(request: TaskActionExecuteRequest) -> TaskActionExecuteResponse:
    try:
        return task_action_execution_service.execute(request)
    except TaskActionExecutionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to execute prepared task action")
        raise HTTPException(status_code=500, detail=f"Action execution failed: {error}") from error


@router.post("/file/scan", response_model=FileSnapshotResponse)
def scan_file_task(request: FileTaskScanRequest) -> FileSnapshotResponse:
    try:
        return file_snapshot_service.scan_folder(
            root_path=request.root_path,
            max_depth=request.max_depth,
            max_files=request.max_files,
            include_hidden=request.include_hidden,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to scan file task folder")
        raise HTTPException(status_code=500, detail=f"Folder scan failed: {error}") from error


@router.post("/file/prepare", response_model=FileTaskPlan)
def prepare_file_task(request: FileTaskPrepareRequest) -> FileTaskPlan:
    try:
        return file_task_planner_service.prepare_deterministic_file_plan(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare file task preview")
        raise HTTPException(status_code=500, detail=f"File task preview failed: {error}") from error


@router.post("/file/plan-with-llm", response_model=FileTaskPlan)
def plan_browser_file_task_with_llm(request: FileTaskLlmPlanRequest) -> FileTaskPlan:
    try:
        return file_task_llm_planner_service.plan_browser_file_task(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare AI-assisted file task preview")
        raise HTTPException(status_code=500, detail=f"AI file task planning failed: {error}") from error


@router.post("/files/search", response_model=IndexedFileSearchResponse)
def search_indexed_files(request: IndexedFileSearchRequest) -> IndexedFileSearchResponse:
    try:
        return file_index_service.search(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to search indexed files")
        raise HTTPException(status_code=500, detail=f"Indexed file search failed: {error}") from error


@router.post("/files/resolve-attachments", response_model=ResolveIndexedAttachmentsResponse)
def resolve_indexed_file_attachments(request: ResolveIndexedAttachmentsRequest) -> ResolveIndexedAttachmentsResponse:
    try:
        return file_index_service.resolve_attachments(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to resolve indexed file attachments")
        raise HTTPException(status_code=500, detail=f"Attachment resolution failed: {error}") from error


@router.post("/document/summary/prepare", response_model=DocumentSummaryPrepareResponse)
def prepare_document_summary_task(request: DocumentSummaryPrepareRequest) -> DocumentSummaryPrepareResponse:
    try:
        return document_summary_task_service.prepare_summary(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare document summary")
        raise HTTPException(status_code=500, detail=f"Document summary preparation failed: {error}") from error


@router.post("/document/summary/from-indexed-files", response_model=DocumentSummaryPrepareResponse)
def prepare_document_summary_from_indexed_files(request: IndexedDocumentSummaryPrepareRequest) -> DocumentSummaryPrepareResponse:
    try:
        return document_summary_task_service.prepare_summary_from_indexed_files(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare document summary from indexed files")
        raise HTTPException(status_code=500, detail=f"Indexed document summary preparation failed: {error}") from error


@router.post("/document/summary/save-output", response_model=GeneratedSummarySaveResponse)
def save_generated_document_summary_output(request: GeneratedSummarySaveRequest) -> GeneratedSummarySaveResponse:
    try:
        return document_summary_task_service.save_output(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to save generated summary output")
        raise HTTPException(status_code=500, detail=f"Generated summary save failed: {error}") from error


@router.post("/logs/analyze/prepare", response_model=LogAnalysisPrepareResponse)
def prepare_log_analysis_report(request: LogAnalysisPrepareRequest) -> LogAnalysisPrepareResponse:
    try:
        return log_analysis_task_service.prepare(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare log analysis report")
        raise HTTPException(status_code=500, detail=f"Log analysis failed: {error}") from error


@router.post("/logs/analyze/save", response_model=GeneratedSummarySaveResponse)
def save_log_analysis_report(request: LogAnalysisSaveRequest) -> GeneratedSummarySaveResponse:
    try:
        return log_analysis_task_service.save(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to save log analysis report")
        raise HTTPException(status_code=500, detail=f"Log analysis report save failed: {error}") from error


@router.post("/document/summary/complete", response_model=DocumentSummaryCompleteResponse)
def complete_document_summary_task(request: DocumentSummaryCompleteRequest) -> DocumentSummaryCompleteResponse:
    try:
        return document_summary_task_service.complete_summary(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to record document summary completion")
        raise HTTPException(status_code=500, detail=f"Document summary completion failed: {error}") from error


@router.post("/gmail/draft/prepare", response_model=GmailDraftPrepareResponse)
def prepare_gmail_draft_task(request: GmailDraftPrepareRequest) -> GmailDraftPrepareResponse:
    try:
        return gmail_draft_planner.prepare(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare Gmail draft")
        raise HTTPException(status_code=500, detail=f"Gmail draft preparation failed: {error}") from error


@router.post("/jira/issue/prepare", response_model=JiraIssueDraftResponse)
def prepare_jira_issue_task(request: JiraIssueDraftRequest) -> JiraIssueDraftResponse:
    try:
        return jira_issue_planner_service.prepare(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Failed to prepare Jira issue")
        raise HTTPException(status_code=500, detail=f"Jira issue preparation failed: {error}") from error


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
