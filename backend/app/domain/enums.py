from enum import Enum


class EventSource(str, Enum):
    mindos = "mindos"
    manual = "manual"
    file_system = "file_system"
    vscode = "vscode"
    browser = "browser"
    vscode_extension = "vscode_extension"
    browser_extension = "browser_extension"
    activity_tracker = "activity_tracker"
    local_agent = "local_agent"
    git = "git"
    github = "github"
    jira = "jira"
    logs = "logs"
    email = "email"


class EventType(str, Enum):
    note = "note"
    file_activity = "file_activity"
    code_activity = "code_activity"
    browser_activity = "browser_activity"
    issue_activity = "issue_activity"
    log_activity = "log_activity"
    email_activity = "email_activity"


class EmbeddingStatus(str, Enum):
    not_required = "not_required"
    pending = "pending"
    indexed = "indexed"
    failed = "failed"


class TaskStatus(str, Enum):
    pending = "pending"
    confirmation_required = "confirmation_required"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskType(str, Enum):
    suggest_branch_name = "suggest_branch_name"
    generate_commit_message = "generate_commit_message"
    create_jira_ticket = "create_jira_ticket"
    draft_email = "draft_email"
    create_pull_request = "create_pull_request"
    weekly_report = "weekly_report"
    unknown = "unknown"


class PermissionLevel(str, Enum):
    read_only = "read_only"
    suggest_only = "suggest_only"
    write_with_confirmation = "write_with_confirmation"
    dangerous_requires_manual_review = "dangerous_requires_manual_review"
