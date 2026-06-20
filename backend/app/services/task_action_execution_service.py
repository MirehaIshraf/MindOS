from datetime import datetime, timezone
from typing import Any

from app.core.dependencies import get_task_repository
from app.domain.enums import TaskStatus, TaskType
from app.repositories.base import TaskRepository
from app.schemas.email import EmailDraftRequest, EmailReplyDraftRequest
from app.schemas.gmail import GmailDraftRequest, GmailSendRequest
from app.schemas.jira import JiraIssueCreateRequest
from app.schemas.task_actions import TaskActionExecuteRequest, TaskActionExecuteResponse
from app.services.email_service import email_service
from app.services.gmail_service import gmail_service
from app.services.jira_service import jira_service
from app.services.task_action_capability_service import task_action_capability_service


class TaskActionExecutionError(ValueError):
    pass


class TaskActionExecutionService:
    def __init__(self, task_repository: TaskRepository | None = None) -> None:
        self._task_repository = task_repository or get_task_repository()

    def capabilities(self):
        return task_action_capability_service.registry()

    def execute(self, request: TaskActionExecuteRequest) -> TaskActionExecuteResponse:
        if request.confirmation is not True:
            raise TaskActionExecutionError("User confirmation is required before executing this action.")

        capability_key = self._capability_key_for_action(request.action_type)
        capabilities = task_action_capability_service.registry().capabilities
        capability = capabilities.get(capability_key)
        if capability is None:
            raise TaskActionExecutionError("Unsupported action type.")
        if not capability.available:
            raise TaskActionExecutionError(capability.reason or "Required action capability is not available.")

        if request.action_type == "gmail.createDraft":
            return self._execute_create_draft(request.preview, capability.provider, request.action_id)
        if request.action_type == "gmail.sendEmail":
            return self._execute_send_email(request.preview, request.action_id)
        if request.action_type == "gmail.replyDraft":
            return self._execute_reply_draft(request.preview, request.action_id)
        if request.action_type == "jira.createIssue":
            return self._execute_create_jira_issue(request.preview, request.action_id)

        raise TaskActionExecutionError("This action is preview-only for now.")

    def _execute_create_draft(self, preview: dict[str, Any], provider: str, action_id: str) -> TaskActionExecuteResponse:
        to = str(preview.get("to") or "").strip()
        subject = str(preview.get("subject") or "").strip()
        body = str(preview.get("body") or "").strip()
        if not subject or not body:
            raise TaskActionExecutionError("Draft subject and body are required.")
        if provider == "gmail" and not to:
            raise TaskActionExecutionError("A recipient is required before creating a Gmail draft.")

        if provider == "email_mcp":
            draft = email_service.create_draft(EmailDraftRequest(to=to, subject=subject, body=body, provider="email_mcp"))
            result = {"provider": "email_mcp", "draft_id": draft.draft_id, "url": draft.url}
            message = draft.message or "Draft created. It was not sent."
        else:
            draft = gmail_service.create_draft(GmailDraftRequest(to=to, subject=subject, body=body, cc=_string_list(preview.get("cc")), bcc=_string_list(preview.get("bcc"))))
            result = {"provider": "gmail", "draft_id": draft.draft_id, "message_id": draft.message_id}
            message = draft.message or "Draft created in Gmail. It was not sent."

        task = self._task_repository.create_task_log(
            task_type=TaskType.draft_email.value,
            instruction="Create Gmail draft",
            status=TaskStatus.completed.value,
            preview={
                "action_id": action_id,
                "action_type": "gmail.createDraft",
                "to": to,
                "subject": subject,
                "body_chars": len(body),
                "provider": result["provider"],
            },
            result={**result, "sent": False},
        )
        self._task_repository.update_task_log(task.id, completed_at=datetime.now(timezone.utc))
        return TaskActionExecuteResponse(
            ok=True,
            status="completed",
            result={**result, "sent": False, "completed_at": datetime.now(timezone.utc).isoformat()},
            message=message,
        )

    def _execute_send_email(self, preview: dict[str, Any], action_id: str) -> TaskActionExecuteResponse:
        to = str(preview.get("to") or "").strip()
        subject = str(preview.get("subject") or "").strip()
        body = str(preview.get("body") or "").strip()
        if not to or not subject or not body:
            raise TaskActionExecutionError("Recipient, subject, and body are required before sending email.")
        result = gmail_service.send_message(
            GmailSendRequest(
                to=[to],
                subject=subject,
                body=body,
                cc=_string_list(preview.get("cc")),
                bcc=_string_list(preview.get("bcc")),
                confirmation=True,
            )
        )
        task = self._task_repository.create_task_log(
            task_type=TaskType.draft_email.value,
            instruction="Send Gmail email",
            status=TaskStatus.completed.value,
            preview={
                "action_id": action_id,
                "action_type": "gmail.sendEmail",
                "to": to,
                "subject": subject,
                "body_chars": len(body),
                "provider": "gmail",
            },
            result={"provider": "gmail", "message_id": result.message_id, "sent": True},
        )
        self._task_repository.update_task_log(task.id, completed_at=datetime.now(timezone.utc))
        return TaskActionExecuteResponse(
            ok=True,
            status="completed",
            result={"provider": "gmail", "message_id": result.message_id, "sent": True},
            message=result.message,
        )

    def _execute_reply_draft(self, preview: dict[str, Any], action_id: str) -> TaskActionExecuteResponse:
        message_id = str(preview.get("message_id") or "").strip()
        body = str(preview.get("body") or "").strip()
        if not message_id or not body:
            raise TaskActionExecutionError("Original message id and reply body are required.")
        result = email_service.create_reply_draft(
            EmailReplyDraftRequest(
                message_id=message_id,
                body=body,
                to=str(preview.get("to") or ""),
                subject=str(preview.get("subject") or ""),
            )
        )
        task = self._task_repository.create_task_log(
            task_type=TaskType.draft_email.value,
            instruction="Create Gmail reply draft",
            status=TaskStatus.completed.value,
            preview={
                "action_id": action_id,
                "action_type": "gmail.replyDraft",
                "message_id": message_id,
                "subject": str(preview.get("subject") or ""),
                "body_chars": len(body),
                "provider": "email_mcp",
            },
            result={"provider": "email_mcp", "draft_id": result.draft_id, "sent": False},
        )
        self._task_repository.update_task_log(task.id, completed_at=datetime.now(timezone.utc))
        return TaskActionExecuteResponse(
            ok=True,
            status="completed",
            result={"provider": "email_mcp", "draft_id": result.draft_id, "url": result.url, "sent": False},
            message=result.message,
        )

    def _execute_create_jira_issue(self, preview: dict[str, Any], action_id: str) -> TaskActionExecuteResponse:
        project_key = str(preview.get("project_key") or preview.get("projectKey") or "").strip().upper()
        issue_type = str(preview.get("issue_type") or preview.get("issueType") or "Task").strip()
        summary = str(preview.get("summary") or "").strip()
        description = str(preview.get("description") or "").strip()
        labels = _string_list(preview.get("labels"))
        priority = str(preview.get("priority") or "").strip() or None
        if not project_key or not issue_type or not summary or not description:
            raise TaskActionExecutionError("Project key, issue type, summary, and description are required before creating a Jira issue.")
        created = jira_service.create_issue(
            JiraIssueCreateRequest(
                project_key=project_key,
                issue_type=issue_type,
                summary=summary,
                description=description,
                labels=labels,
                priority=priority,
                confirmation=True,
            )
        )
        task = self._task_repository.create_task_log(
            task_type=TaskType.create_jira_ticket.value,
            instruction="Create Jira issue",
            status=TaskStatus.completed.value,
            preview={
                "action_id": action_id,
                "action_type": "jira.createIssue",
                "project_key": project_key,
                "issue_type": issue_type,
                "summary": summary,
                "description_chars": len(description),
                "labels": labels,
            },
            result={
                "issue_key": created.issue_key,
                "url": created.url,
                "project_key": project_key,
                "issue_type": issue_type,
                "labels": labels,
            },
        )
        self._task_repository.update_task_log(task.id, completed_at=datetime.now(timezone.utc))
        return TaskActionExecuteResponse(
            ok=True,
            status="completed",
            result={
                "issue_key": created.issue_key,
                "url": created.url,
                "project_key": project_key,
                "issue_type": issue_type,
                "labels": labels,
            },
            message=f"Created Jira issue {created.issue_key}.",
        )

    def _capability_key_for_action(self, action_type: str) -> str:
        if action_type == "gmail.createDraft":
            return "gmail.createDraft"
        if action_type == "gmail.sendEmail":
            return "gmail.sendEmail"
        if action_type == "gmail.replyDraft":
            return "gmail.replyDraft"
        if action_type == "gmail.sendDraft":
            return "gmail.send"
        if action_type == "github.createIssue":
            return "github.createIssue"
        if action_type == "github.createPullRequest":
            return "github.createPullRequest"
        if action_type == "jira.searchIssues":
            return "jira.searchIssues"
        if action_type == "jira.createIssue":
            return "jira.createIssue"
        if action_type == "git.commit":
            return "git.commit"
        if action_type == "git.push":
            return "git.push"
        raise TaskActionExecutionError("Unsupported action type.")


task_action_execution_service = TaskActionExecutionService()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []
