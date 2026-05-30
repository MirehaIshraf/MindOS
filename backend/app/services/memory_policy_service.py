CAPTURED_SOURCES = {
    "file_system",
    "logs",
    "git",
    "jira",
    "github",
    "email",
    "browser",
    "vscode",
    "vscode_extension",
    "browser_extension",
    "manual",
}


def get_memory_policy_for_event(source: str, type: str, metadata: dict | None = None) -> dict[str, object]:
    event_type = type or ""
    source_value = source or ""

    if event_type in {"chat_message", "chat_response"}:
        return {
            "memory_category": "chat",
            "hidden_from_default": True,
            "is_indexable": False,
            "is_relationship_eligible": False,
            "is_context_eligible": False,
        }

    if event_type == "chat_summary":
        return _policy("chat", hidden=False)

    if event_type.startswith("task_"):
        return _policy("task", hidden=False)

    if event_type == "report_generated":
        return _policy("report", hidden=False)

    if source_value == "activity_tracker":
        return {
            "memory_category": "activity",
            "hidden_from_default": True,
            "is_indexable": False,
            "is_relationship_eligible": False,
            "is_context_eligible": False,
        }

    if source_value == "browser_extension" and bool((metadata or {}).get("private")):
        policy = _policy("captured_event", hidden=True)
        return policy

    if source_value == "local_agent":
        if event_type in {"agent_summary", "agent_action_result"}:
            return _policy("agent", hidden=False)
        if event_type in {"agent_observation", "agent_decision", "agent_action_preview"}:
            return {
                "memory_category": "agent",
                "hidden_from_default": True,
                "is_indexable": False,
                "is_relationship_eligible": False,
                "is_context_eligible": False,
            }
        return _policy("agent", hidden=True)

    if source_value in CAPTURED_SOURCES:
        return _policy("captured_event", hidden=False)

    if source_value == "mindos":
        category = str((metadata or {}).get("memory_category") or "mindos")
        return _policy(category, hidden=False)

    return _policy("captured_event", hidden=False)


def apply_memory_policy(event_data: dict) -> dict:
    metadata = event_data.get("metadata") or {}
    source = event_data.get("source")
    source_value = source.value if hasattr(source, "value") else str(source)
    policy = get_memory_policy_for_event(source_value, str(event_data.get("type", "")), metadata)
    merged = dict(event_data)
    for key, value in policy.items():
        merged[key] = value
    metadata = dict(metadata)
    metadata.setdefault("memory_category", policy["memory_category"])
    metadata.setdefault("hidden_from_default", policy["hidden_from_default"])
    merged["metadata"] = metadata
    return merged


def _policy(category: str, hidden: bool) -> dict[str, object]:
    return {
        "memory_category": category,
        "hidden_from_default": hidden,
        "is_indexable": True,
        "is_relationship_eligible": True,
        "is_context_eligible": True,
    }
