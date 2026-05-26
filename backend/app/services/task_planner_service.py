import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.domain.enums import TaskType
from app.schemas.context import ContextPackage
from app.schemas.tasks import TaskPlan, TaskPlanningRequest, TaskPlanningResponse
from app.services.context_builder_service import ContextBuilderService
from app.services.model_router_service import model_router_service

PLANNER_PROMPT = """/no_think

You are MindOS task planner.

You do not execute actions.
You only prepare a structured task plan from the user's instruction and local memory context.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations outside JSON.
Do not include hidden reasoning.

Required JSON shape:
{
  "task_type": "...",
  "confidence": 0.0,
  "title": null,
  "description": null,
  "priority": null,
  "recipient": null,
  "subject": null,
  "body": null,
  "repo": null,
  "branch_name": null,
  "commit_message": null,
  "pr_title": null,
  "pr_body": null,
  "report_markdown": null,
  "evidence": [{"source": "...", "title": "...", "reason": "..."}],
  "missing_fields": [],
  "safety_notes": []
}

Rules:
- Use only provided local memory context.
- Do not invent files, tickets, commits, logs, emails, or people.
- If recipient/repo/branch is missing, set it to null and add it to missing_fields.
- For write-like tasks, add a safety note that user confirmation is required.
- For Jira tickets, create a clear title, description, and priority.
- For emails, create subject/body but do not claim it was sent.
- For PRs, create pr_title/pr_body but do not claim it was opened.
- For commit messages, create a concise conventional commit message.
- For branch names, create a lowercase slash-style branch name.
- For weekly report, create report_markdown.
"""

PRIORITIES = {"Low", "Medium", "High", "Critical"}
WRITE_LIKE_TASKS = {TaskType.create_jira_ticket, TaskType.draft_email, TaskType.create_pull_request}
logger = logging.getLogger(__name__)
TASK_PLAN_FIELDS = {
    "task_type",
    "confidence",
    "title",
    "description",
    "priority",
    "recipient",
    "subject",
    "body",
    "repo",
    "branch_name",
    "commit_message",
    "pr_title",
    "pr_body",
    "report_markdown",
    "evidence",
    "missing_fields",
    "safety_notes",
    "planner_model",
    "planner_provider",
    "planner_warning",
    "context_stats",
}

TASK_PLAN_DEFAULTS: dict[str, Any] = {
    "task_type": TaskType.unknown.value,
    "confidence": 0.0,
    "title": None,
    "description": None,
    "priority": None,
    "recipient": None,
    "subject": None,
    "body": None,
    "repo": None,
    "branch_name": None,
    "commit_message": None,
    "pr_title": None,
    "pr_body": None,
    "report_markdown": None,
    "evidence": [],
    "missing_fields": [],
    "safety_notes": [],
    "planner_model": None,
    "planner_provider": None,
    "planner_warning": None,
    "context_stats": None,
}


class TaskPlannerService:
    def __init__(self, context_builder: ContextBuilderService | None = None) -> None:
        self._context_builder = context_builder or ContextBuilderService()

    def plan_task(self, request: TaskPlanningRequest) -> TaskPlanningResponse:
        task_type = classify_task(request.instruction)
        if request.task_type:
            task_type = coerce_task_type(request.task_type) or task_type

        context_package = (
            self._context_builder.build_task_context(
                request.instruction,
                limit=5,
                related_per_event=1,
            )
            if request.use_context
            else empty_context_package(request.instruction)
        )

        warning = None
        route_result = None
        try:
            route_result = model_router_service.generate(
                messages=[
                    {"role": "system", "content": PLANNER_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Task type decided by FastAPI: {task_type.value}\n"
                            f"Instruction: {request.instruction}\n\n"
                            f"Local memory context:\n{self._context_builder.format_context_for_llm(context_package)}"
                        ),
                    },
                ],
                requested_model_id=request.model_id,
                options={"context_package": context_package},
            )
            plan = validate_plan(parse_json_plan(route_result.reply), task_type, context_package)
            warning = route_result.warning
        except Exception:
            logger.exception("Model task planning failed; using deterministic fallback")
            plan = deterministic_plan(task_type, request.instruction, context_package)
            warning = "Model planning failed. Used deterministic fallback."

        return TaskPlanningResponse(
            plan=plan,
            model=route_result.model_used if route_result else "deterministic",
            provider=route_result.provider if route_result else "deterministic",
            warning=warning,
            context_summary=context_package.summary,
            context_stats=context_stats(context_package),
        )


def classify_task(instruction: str) -> TaskType:
    text = instruction.lower().strip()
    if "branch name" in text or text.startswith("suggest branch"):
        return TaskType.suggest_branch_name
    if "commit message" in text or "generate commit" in text:
        return TaskType.generate_commit_message
    if ("jira" in text or "ticket" in text) and any(word in text for word in ["create", "draft", "make", "prepare", "open"]):
        return TaskType.create_jira_ticket
    if "email" in text and any(word in text for word in ["draft", "write", "send", "prepare"]):
        return TaskType.draft_email
    if "pull request" in text or "create pr" in text or "raise pr" in text or " pr " in f" {text} ":
        return TaskType.create_pull_request
    if "weekly report" in text or "report" in text:
        return TaskType.weekly_report
    return TaskType.unknown


def coerce_task_type(value: str) -> TaskType | None:
    try:
        return TaskType(value)
    except ValueError:
        return None


def parse_json_plan(text: str) -> dict[str, Any]:
    cleaned = text.strip().replace("/no_think", "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def validate_plan(raw: dict[str, Any], task_type: TaskType, context_package: ContextPackage) -> TaskPlan:
    raw = dict(raw)
    raw["task_type"] = task_type.value
    priority = raw.get("priority")
    if isinstance(priority, str):
        normalized_priority = priority.strip().title()
        raw["priority"] = normalized_priority if normalized_priority in PRIORITIES else "Medium"
    raw["branch_name"] = sanitize_branch_name(raw.get("branch_name"))
    raw["evidence"] = filter_evidence(raw.get("evidence") or [], context_package)
    if task_type in WRITE_LIKE_TASKS:
        notes = list(raw.get("safety_notes") or [])
        if not any("confirmation" in str(note).lower() for note in notes):
            notes.append("User confirmation is required before execution.")
        notes.append("Current execution is mock-only.")
        raw["safety_notes"] = list(dict.fromkeys(notes))
    try:
        return build_task_plan_safely(raw)
    except (TypeError, ValueError, ValidationError):
        return deterministic_plan(task_type, "", context_package)


def deterministic_plan(task_type: TaskType, instruction: str, context_package: ContextPackage) -> TaskPlan:
    summary = context_package.summary
    title = infer_title(instruction, context_package)
    branch_name = infer_branch_name(instruction, context_package)
    commit_message = infer_commit_message(instruction, context_package)
    evidence = build_evidence(context_package)
    notes = ["Current execution is mock-only."]
    if task_type in WRITE_LIKE_TASKS:
        notes.insert(0, "User confirmation is required before execution.")

    base = {
        "task_type": task_type.value,
        "confidence": 0.55 if task_type != TaskType.unknown else 0.0,
        "evidence": evidence,
        "missing_fields": [],
        "safety_notes": notes,
    }
    if task_type == TaskType.suggest_branch_name:
        return build_task_plan_safely(base, {"branch_name": branch_name})
    if task_type == TaskType.generate_commit_message:
        return build_task_plan_safely(base, {"commit_message": commit_message})
    if task_type == TaskType.weekly_report:
        return build_task_plan_safely(base, {"report_markdown": build_report(context_package)})
    if task_type == TaskType.create_jira_ticket:
        return build_task_plan_safely(
            base,
            {"title": title, "description": build_description(instruction, summary), "priority": "Medium"},
        )
    if task_type == TaskType.draft_email:
        return build_task_plan_safely(
            base,
            {"recipient": None, "subject": title, "body": build_description(instruction, summary), "missing_fields": ["recipient"]},
        )
    if task_type == TaskType.create_pull_request:
        return build_task_plan_safely(
            base,
            {
                "repo": None,
                "pr_title": title,
                "pr_body": build_description(instruction, summary),
                "branch_name": branch_name,
                "missing_fields": ["repo"],
            },
        )
    return build_task_plan_safely(
        base,
        {"missing_fields": ["task_type"], "safety_notes": ["I could not classify this task yet."]},
    )


def build_task_plan_safely(data: dict[str, Any], overrides: dict[str, Any] | None = None) -> TaskPlan:
    plan_data = dict(TASK_PLAN_DEFAULTS)
    if isinstance(data, dict):
        plan_data.update({key: value for key, value in data.items() if key in TASK_PLAN_FIELDS})
    if overrides:
        plan_data.update({key: value for key, value in overrides.items() if key in TASK_PLAN_FIELDS})

    task_type = plan_data.get("task_type") or TaskType.unknown.value
    plan_data["task_type"] = task_type.value if isinstance(task_type, TaskType) else str(task_type)
    try:
        plan_data["confidence"] = max(0.0, min(float(plan_data.get("confidence") or 0.0), 1.0))
    except (TypeError, ValueError):
        plan_data["confidence"] = 0.0

    for key in ("evidence", "missing_fields", "safety_notes"):
        value = plan_data.get(key)
        if not isinstance(value, list):
            plan_data[key] = []

    plan_data["evidence"] = [
        item if isinstance(item, dict) else {"source": "memory", "title": str(item), "reason": ""}
        for item in plan_data["evidence"]
        if item is not None
    ]
    plan_data["missing_fields"] = [str(item) for item in plan_data["missing_fields"] if item]
    plan_data["safety_notes"] = [str(item) for item in plan_data["safety_notes"] if item]
    return TaskPlan(**plan_data)


def filter_evidence(evidence: list[Any], context_package: ContextPackage) -> list[dict[str, Any]]:
    valid_titles = {event.title for event in [*context_package.direct_events, *context_package.related_events]}
    filtered = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title and valid_titles and title not in valid_titles:
            continue
        filtered.append(
            {
                "source": str(item.get("source") or "memory"),
                "title": title or "Memory item",
                "reason": str(item.get("reason") or "Relevant local memory."),
            }
        )
    return filtered[:5] or build_evidence(context_package)


def build_evidence(context_package: ContextPackage) -> list[dict[str, Any]]:
    events = [*context_package.direct_events, *context_package.related_events]
    return [
        {"source": event.source, "title": event.title, "reason": event.match_reason or "Relevant local memory."}
        for event in events[:5]
    ]


def sanitize_branch_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    branch = value.strip().lower().replace(" ", "-").replace("_", "-")
    branch = re.sub(r"[^a-z0-9./-]+", "", branch)
    branch = re.sub(r"-+", "-", branch).strip("-/.")
    return branch or None


def context_stats(context_package: ContextPackage) -> dict[str, Any]:
    return {
        "direct_count": len(context_package.direct_events),
        "related_count": len(context_package.related_events),
        "relationship_count": len(context_package.relationships),
        "sources": [group.source for group in context_package.source_groups],
        "token_estimate": context_package.token_estimate,
        "warnings": context_package.warnings,
    }


def empty_context_package(query: str) -> ContextPackage:
    return ContextPackage(
        query=query,
        direct_events=[],
        related_events=[],
        relationships=[],
        source_groups=[],
        summary="No local memory context was requested.",
        token_estimate=0,
        warnings=[],
    )


def context_events(context_package: ContextPackage):
    return [*context_package.direct_events, *context_package.related_events]


def infer_title(instruction: str, context_package: ContextPackage) -> str:
    events = context_events(context_package)
    if events:
        return events[0].title
    return instruction.strip().rstrip(".")[:80] or "Prepared MindOS task"


def infer_branch_name(instruction: str, context_package: ContextPackage) -> str:
    events = context_events(context_package)
    text = f"{instruction} {' '.join(event.title for event in events[:3])}".lower()
    if "jwt" in text or "login" in text or "auth" in text:
        return "fix/jwt-login-expiry"
    words = [re.sub(r"[^a-z0-9-]", "", word) for word in text.replace("_", "-").split()]
    words = [word for word in words if word][:4]
    return "work/" + "-".join(words or ["mindos-task"])


def infer_commit_message(instruction: str, context_package: ContextPackage) -> str:
    events = context_events(context_package)
    text = f"{instruction} {' '.join(event.title for event in events[:3])}".lower()
    if "jwt" in text or "auth" in text or "login" in text:
        return "fix(auth): handle expired JWT refresh flow"
    return "chore: update local work context"


def build_description(instruction: str, summary: str) -> str:
    return f"{instruction.strip()}\n\nContext:\n{summary}"


def build_report(context_package: ContextPackage) -> str:
    events = context_events(context_package)
    activity = "\n".join(f"- {event.title} ({event.source})" for event in events[:8]) or "- No matching activity found."
    sources = ", ".join(group.source for group in context_package.source_groups) or "none"
    return (
        "# Weekly Work Report\n\n"
        f"## Summary\n{context_package.summary}\n\n"
        f"## Sources\n{sources}\n\n"
        f"## Key Activity\n{activity}\n\n"
        "## Issues Found\n- Review related failures or warnings in local memory.\n\n"
        "## Suggested Next Actions\n- Confirm priorities and prepare follow-up tasks if needed."
    )


task_planner_service = TaskPlannerService()
