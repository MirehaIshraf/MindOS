from app.domain.models import Event

CAPTURED_SOURCES = {
    "manual",
    "file_system",
    "vscode",
    "browser",
    "github",
    "jira",
    "logs",
    "email",
}

CHAT_EVENT_TYPES = {"chat_message", "chat_response"}


def get_memory_category(event: Event) -> str:
    if event.memory_category:
        return event.memory_category
    if event.type in CHAT_EVENT_TYPES:
        return "chat"
    if event.type.startswith("task_"):
        return "task"
    if event.type == "report_generated":
        return "report"
    if event.source.value in CAPTURED_SOURCES:
        return "captured_event"
    if event.source.value == "mindos":
        return "mindos"
    return "unknown"


def is_hidden_from_default_memory(event: Event) -> bool:
    if event.hidden_from_default:
        return True
    return event.type in CHAT_EVENT_TYPES
