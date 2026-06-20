import html
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from app.core.dependencies import get_event_repository, get_relationship_repository
from app.schemas.connectors import (
    BrowserConnectorRuntimeResponse,
    BrowserHeartbeatRequest,
    BrowserHeartbeatResponse,
    BrowserRulesResponse,
    ConnectorConfigResponse,
    ConnectorConfigUpdateRequest,
    ConnectorListResponse,
    ConnectorSourceCreateRequest,
    ConnectorSourceResponse,
    ConnectorSourcesResponse,
    ConnectorSourceUpdateRequest,
    ConnectorStatusResponse,
    ConnectorToggleRequest,
    ConnectorToggleResponse,
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
    VSCodeConnectorRuntimeResponse,
    VSCodeHeartbeatRequest,
    VSCodeHeartbeatResponse,
)
from app.schemas.ingest import CollectorClientsResponse
from app.schemas.email import (
    EmailCapabilityResponse,
    EmailConnectResponse,
    EmailDisconnectResponse,
    EmailDraftRequest,
    EmailDraftResponse,
    EmailMcpConfigRequest,
    EmailReplyDraftRequest,
    EmailSearchRequest,
    EmailSearchResponse,
    EmailSendRequest,
    EmailSendResponse,
    EmailStatusResponse,
    EmailSyncRequest,
    EmailSyncResponse,
    EmailTestResponse,
)
from app.schemas.github import (
    GitHubConfigRequest,
    GitHubReposResponse,
    GitHubSelectionRequest,
    GitHubStatusResponse,
    GitHubSyncRequest,
    GitHubSyncResponse,
    GitHubTestResponse,
)
from app.schemas.jira import (
    JiraConfigRequest,
    JiraConnectionResponse,
    JiraIssueCreateRequest,
    JiraIssueCreateResponse,
    JiraIssueSearchRequest,
    JiraIssueSearchResponse,
    JiraProjectsResponse,
    JiraStatusResponse,
    JiraTestResponse,
)
from app.schemas.file_index import (
    FileIndexJobResponse,
    FileIndexJobsResponse,
    TrackedFolderCreateRequest,
    TrackedFolderResponse,
    TrackedFoldersResponse,
    TrackedFolderUpdateRequest,
)
from app.schemas.gmail import (
    GeneratedOutputAttachmentReference,
    GmailConnectResponse,
    GmailCredentialsUploadRequest,
    GmailDraftRequest,
    GmailDraftResponse,
    GmailRecentEmailsResponse,
    GmailSendRequest,
    GmailSendDraftResponse,
    GmailSendResponse,
    GmailStatusResponse,
    GmailTestResponse,
)
from app.schemas.file_index import IndexedFileAttachmentReference
from app.services.connector_source_service import connector_source_service
from app.services.connector_registry_service import connector_registry_service
from app.services.connector_service import ConnectorService
from app.services.email_service import EmailCapabilityUnavailableError, EmailConnectorError, email_service
from app.services.external_ingest_service import external_ingest_service
from app.services.file_import_service import FileImportService
from app.services.git_import_service import GitImportService
from app.services.github_service import GitHubConnectorError, github_service
from app.services.gmail_service import GmailConnectorError, gmail_service
from app.services.jira_service import JiraConnectorError, jira_service
from app.services.file_index_scheduler_service import file_index_scheduler_service
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


@router.get("/vscode/runtime", response_model=VSCodeConnectorRuntimeResponse)
def get_vscode_runtime() -> VSCodeConnectorRuntimeResponse:
    return connector_registry_service.get_vscode_runtime()


@router.post("/vscode/heartbeat", response_model=VSCodeHeartbeatResponse)
def record_vscode_heartbeat(request: VSCodeHeartbeatRequest) -> VSCodeHeartbeatResponse:
    return connector_registry_service.record_vscode_heartbeat(request)


@router.get("/browser/runtime", response_model=BrowserConnectorRuntimeResponse)
def get_browser_runtime() -> BrowserConnectorRuntimeResponse:
    return connector_registry_service.get_browser_runtime()


@router.post("/browser/heartbeat", response_model=BrowserHeartbeatResponse)
def record_browser_heartbeat(request: BrowserHeartbeatRequest) -> BrowserHeartbeatResponse:
    return connector_registry_service.record_browser_heartbeat(request)


@router.get("/browser/rules", response_model=BrowserRulesResponse)
def get_browser_rules() -> BrowserRulesResponse:
    return connector_registry_service.get_browser_rules()


@router.get("/github/status", response_model=GitHubStatusResponse)
def get_github_status() -> GitHubStatusResponse:
    return github_service.status()


@router.post("/github/config", response_model=GitHubStatusResponse)
def save_github_config(request: GitHubConfigRequest) -> GitHubStatusResponse:
    return github_service.save_config(request)


@router.post("/github/test", response_model=GitHubTestResponse)
def test_github_connection() -> GitHubTestResponse:
    try:
        return github_service.test_connection()
    except GitHubConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/github/repos", response_model=GitHubReposResponse)
def list_github_repos() -> GitHubReposResponse:
    try:
        return github_service.list_repos()
    except GitHubConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/github/selection", response_model=GitHubStatusResponse)
def save_github_selection(request: GitHubSelectionRequest) -> GitHubStatusResponse:
    try:
        return github_service.save_selection(request)
    except (GitHubConnectorError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/github/sync", response_model=GitHubSyncResponse)
def sync_github(request: GitHubSyncRequest) -> GitHubSyncResponse:
    try:
        return github_service.sync(request)
    except (GitHubConnectorError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/github/events")
def clear_github_events() -> dict[str, object]:
    return _clear_events_for_source("github")


@router.get("/jira/status", response_model=JiraStatusResponse)
def get_jira_status() -> JiraStatusResponse:
    return jira_service.status()


@router.post("/jira/config", response_model=JiraStatusResponse)
def save_jira_config(request: JiraConfigRequest) -> JiraStatusResponse:
    return jira_service.save_config(request)


@router.post("/jira/test", response_model=JiraTestResponse)
def test_jira_connection() -> JiraTestResponse:
    try:
        return jira_service.test_connection()
    except JiraConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/jira/connect", response_model=JiraConnectionResponse)
def connect_jira() -> JiraConnectionResponse:
    try:
        return jira_service.connect()
    except JiraConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/jira/disconnect", response_model=JiraConnectionResponse)
def disconnect_jira() -> JiraConnectionResponse:
    return jira_service.disconnect()


@router.delete("/jira/credentials", response_model=JiraStatusResponse)
def remove_jira_credentials() -> JiraStatusResponse:
    return jira_service.remove_credentials()


@router.get("/jira/projects", response_model=JiraProjectsResponse)
def list_jira_projects() -> JiraProjectsResponse:
    try:
        return jira_service.list_projects()
    except JiraConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/jira/search", response_model=JiraIssueSearchResponse)
def search_jira_issues(request: JiraIssueSearchRequest) -> JiraIssueSearchResponse:
    try:
        return jira_service.search_issues(request)
    except (JiraConnectorError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/jira/issues", response_model=JiraIssueCreateResponse)
def create_jira_issue(request: JiraIssueCreateRequest) -> JiraIssueCreateResponse:
    try:
        return jira_service.create_issue(request)
    except (JiraConnectorError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/email/status", response_model=EmailStatusResponse)
def get_email_status() -> EmailStatusResponse:
    return email_service.status()


@router.post("/email/config", response_model=EmailStatusResponse)
def save_email_config(request: EmailMcpConfigRequest) -> EmailStatusResponse:
    try:
        return email_service.save_config(request)
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/test", response_model=EmailTestResponse)
def test_email_connection() -> EmailTestResponse:
    try:
        return email_service.test_connection()
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/connect", response_model=EmailConnectResponse)
def connect_email() -> EmailConnectResponse:
    try:
        return email_service.connect()
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/disconnect", response_model=EmailDisconnectResponse)
def disconnect_email() -> EmailDisconnectResponse:
    return email_service.disconnect()


@router.get("/email/capabilities", response_model=EmailCapabilityResponse)
def get_email_capabilities() -> EmailCapabilityResponse:
    try:
        return email_service.capabilities()
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/sync", response_model=EmailSyncResponse)
def sync_email(request: EmailSyncRequest) -> EmailSyncResponse:
    try:
        return email_service.sync(request)
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/drafts", response_model=EmailDraftResponse)
def create_email_draft(request: EmailDraftRequest) -> EmailDraftResponse:
    try:
        return email_service.create_draft(request)
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/search", response_model=EmailSearchResponse)
def search_email(request: EmailSearchRequest) -> EmailSearchResponse:
    try:
        return email_service.search_preview(request)
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/send", response_model=EmailSendResponse)
def send_email(request: EmailSendRequest) -> EmailSendResponse:
    try:
        return email_service.send_email(request)
    except EmailCapabilityUnavailableError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/email/reply-draft", response_model=EmailDraftResponse)
def create_email_reply_draft(request: EmailReplyDraftRequest) -> EmailDraftResponse:
    try:
        return email_service.create_reply_draft(request)
    except EmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/email/events")
def clear_email_events() -> dict[str, object]:
    return _clear_events_for_source("email")


@router.get("/gmail/status", response_model=GmailStatusResponse)
def get_gmail_status() -> GmailStatusResponse:
    return gmail_service.status()


@router.post("/gmail/credentials/upload", response_model=GmailStatusResponse)
def upload_gmail_credentials(request: GmailCredentialsUploadRequest) -> GmailStatusResponse:
    try:
        return gmail_service.upload_credentials(request.filename, request.content)
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/gmail/connect", response_model=GmailConnectResponse)
def connect_gmail() -> GmailConnectResponse:
    try:
        auth_url = gmail_service.start_connect()
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return GmailConnectResponse(
        status="connecting",
        auth_url=auth_url,
        message="Open the Google sign-in page to connect Gmail.",
    )


@router.get("/gmail/oauth/callback", response_class=HTMLResponse)
def gmail_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> HTMLResponse:
    try:
        status = gmail_service.complete_oauth_callback(code, state, error)
    except GmailConnectorError as service_error:
        return HTMLResponse(
            content=f"<html><body><h1>Gmail connection failed</h1><p>{html.escape(str(service_error))}</p><p>You can return to MindOS and try again.</p></body></html>",
            status_code=400,
        )
    email = status.email_address or "your account"
    return HTMLResponse(
        content=f"<html><body><h1>Gmail connected</h1><p>Connected {html.escape(email)}. You can return to MindOS.</p></body></html>"
    )


@router.post("/gmail/test", response_model=GmailTestResponse)
def test_gmail_connection() -> GmailTestResponse:
    try:
        return gmail_service.test_connection()
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/gmail/recent", response_model=GmailRecentEmailsResponse)
def list_recent_gmail(limit: int = 5) -> GmailRecentEmailsResponse:
    try:
        return gmail_service.list_recent_emails(limit=limit)
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/gmail/drafts/test", response_model=GmailDraftResponse)
def create_gmail_test_draft() -> GmailDraftResponse:
    try:
        return gmail_service.create_test_draft()
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/gmail/drafts", response_model=GmailDraftResponse)
async def create_gmail_draft(request: Request) -> GmailDraftResponse:
    try:
        if _is_multipart_request(request):
            form = await request.form()
            attachments = await _read_gmail_form_attachments(form.getlist("attachments"))
            attachments.extend(_read_indexed_gmail_attachments(_form_string(form, "indexed_attachments")))
            attachments.extend(_read_generated_gmail_attachments(_form_string(form, "generated_attachments")))
            return gmail_service.create_draft_with_attachments(
                to=_form_string_list(form, "to"),
                cc=_form_string_list(form, "cc"),
                bcc=_form_string_list(form, "bcc"),
                subject=_form_string(form, "subject"),
                body=_form_string(form, "body"),
                attachments=attachments,
            )
        payload = GmailDraftRequest.model_validate(await request.json())
        return gmail_service.create_draft(payload)
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/gmail/send", response_model=GmailSendResponse)
async def send_gmail_message(request: Request) -> GmailSendResponse:
    try:
        if _is_multipart_request(request):
            form = await request.form()
            attachments = await _read_gmail_form_attachments(form.getlist("attachments"))
            attachments.extend(_read_indexed_gmail_attachments(_form_string(form, "indexed_attachments")))
            attachments.extend(_read_generated_gmail_attachments(_form_string(form, "generated_attachments")))
            return gmail_service.send_message_with_attachments(
                to=_form_string_list(form, "to"),
                cc=_form_string_list(form, "cc"),
                bcc=_form_string_list(form, "bcc"),
                subject=_form_string(form, "subject"),
                body=_form_string(form, "body"),
                confirmation=_form_bool(form, "confirmation"),
                attachments=attachments,
            )
        payload = GmailSendRequest.model_validate(await request.json())
        return gmail_service.send_message(payload)
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/gmail/drafts/{draft_id}/send", response_model=GmailSendDraftResponse)
def send_gmail_draft(draft_id: str) -> GmailSendDraftResponse:
    try:
        result = gmail_service.send_draft(draft_id)
    except GmailConnectorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    message_id = str(result.get("id") or "") or None
    return GmailSendDraftResponse(status="sent", draft_id=draft_id, message_id=message_id, message="Draft sent.")


@router.post("/gmail/disconnect", response_model=GmailStatusResponse)
def disconnect_gmail() -> GmailStatusResponse:
    return gmail_service.disconnect()


@router.delete("/gmail/credentials", response_model=GmailStatusResponse)
def remove_gmail_credentials() -> GmailStatusResponse:
    return gmail_service.remove_credentials()


def _is_multipart_request(request: Request) -> bool:
    return "multipart/form-data" in (request.headers.get("content-type") or "").lower()


def _form_string(form: object, key: str) -> str:
    value = form.get(key) if hasattr(form, "get") else None
    if _is_upload_file(value):
        return ""
    return str(value or "").strip()


def _form_string_list(form: object, key: str) -> list[str]:
    values = form.getlist(key) if hasattr(form, "getlist") else []
    result: list[str] = []
    for value in values:
        if _is_upload_file(value):
            continue
        for part in str(value or "").split(","):
            cleaned = part.strip()
            if cleaned:
                result.append(cleaned)
    return result


def _form_bool(form: object, key: str) -> bool:
    value = _form_string(form, key).lower()
    return value in {"1", "true", "yes", "on"}


async def _read_gmail_form_attachments(values: list[object]) -> list[dict[str, object]]:
    attachments: list[dict[str, object]] = []
    for value in values:
        if not _is_upload_file(value):
            continue
        content = await value.read()
        attachments.append(
            {
                "filename": getattr(value, "filename", None) or "attachment",
                "content_type": getattr(value, "content_type", None) or "application/octet-stream",
                "content": content,
                "size": len(content),
            }
        )
    return attachments


def _read_indexed_gmail_attachments(raw_value: str) -> list[dict[str, object]]:
    if not raw_value.strip():
        return []
    try:
        raw_items = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ValueError("Indexed attachment references must be valid JSON.") from error
    if not isinstance(raw_items, list):
        raise ValueError("Indexed attachment references must be a list.")
    references = [IndexedFileAttachmentReference.model_validate(item) for item in raw_items]
    return gmail_service.read_indexed_attachments(references)


def _read_generated_gmail_attachments(raw_value: str) -> list[dict[str, object]]:
    if not raw_value.strip():
        return []
    try:
        raw_items = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ValueError("Generated attachment references must be valid JSON.") from error
    if not isinstance(raw_items, list):
        raise ValueError("Generated attachment references must be a list.")
    references = [GeneratedOutputAttachmentReference.model_validate(item) for item in raw_items]
    return gmail_service.read_generated_attachments(references)


def _is_upload_file(value: object) -> bool:
    return hasattr(value, "read") and hasattr(value, "filename")


@router.get("/file-system/tracked-folders", response_model=TrackedFoldersResponse)
def list_tracked_folders() -> TrackedFoldersResponse:
    return connector_source_service.list_tracked_folders()


@router.post("/file-system/tracked-folders", response_model=TrackedFolderResponse)
def create_tracked_folder(request: TrackedFolderCreateRequest) -> TrackedFolderResponse:
    try:
        folder = connector_source_service.create_tracked_folder(request)
        if folder.enabled and folder.indexing_enabled:
            file_index_scheduler_service.queue_source(folder.id, reason="folder_connected")
        return connector_source_service.tracked_folder(folder.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put("/file-system/tracked-folders/{source_id}", response_model=TrackedFolderResponse)
def update_tracked_folder(source_id: str, request: TrackedFolderUpdateRequest) -> TrackedFolderResponse:
    try:
        folder = connector_source_service.update_tracked_folder(source_id, request)
        if folder.enabled and folder.indexing_enabled:
            file_index_scheduler_service.queue_source(folder.id, reason="folder_updated")
        return connector_source_service.tracked_folder(folder.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Tracked folder not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/file-system/tracked-folders/{source_id}")
def delete_tracked_folder(source_id: str) -> dict[str, str]:
    if not connector_source_service.delete_source(source_id):
        raise HTTPException(status_code=404, detail="Tracked folder not found.")
    return {"status": "deleted"}


@router.post("/file-system/tracked-folders/{source_id}/reindex", response_model=FileIndexJobResponse)
def reindex_tracked_folder(source_id: str) -> FileIndexJobResponse:
    try:
        return file_index_scheduler_service.queue_source(source_id, reason="manual_reindex")
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Tracked folder not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/file-system/index-jobs", response_model=FileIndexJobsResponse)
def list_file_index_jobs() -> FileIndexJobsResponse:
    return file_index_scheduler_service.list_jobs()


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


@router.post("/sources/{source_id}/index")
def index_connector_source(source_id: str) -> dict[str, object]:
    try:
        return connector_source_service.index_source(source_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Saved source not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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


@router.get("/{connector_id}", response_model=ConnectorStatusResponse)
def get_connector(connector_id: str) -> ConnectorStatusResponse:
    try:
        return connector_registry_service.get_connector(connector_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Connector not found.") from error


@router.post("/{connector_id}/toggle", response_model=ConnectorToggleResponse)
def toggle_connector(connector_id: str, request: ConnectorToggleRequest) -> ConnectorToggleResponse:
    try:
        return connector_registry_service.set_enabled(connector_id, request.enabled)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Connector not found.") from error


@router.get("/{connector_id}/config", response_model=ConnectorConfigResponse)
def get_connector_config(connector_id: str) -> ConnectorConfigResponse:
    try:
        return connector_registry_service.get_config(connector_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Connector not found.") from error


@router.post("/{connector_id}/config", response_model=ConnectorConfigResponse)
def update_connector_config(connector_id: str, request: ConnectorConfigUpdateRequest) -> ConnectorConfigResponse:
    try:
        return connector_registry_service.save_config(connector_id, request.config)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Connector not found.") from error
