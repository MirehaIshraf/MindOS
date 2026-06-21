import json
import re


THINKING_PREFIXES = (
    "thinking:",
    "thought:",
    "reasoning:",
    "chain of thought:",
    "let's think step by step",
)


def clean_llm_response(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = cleaned.replace("/no_think", "")
    cleaned = _strip_tool_call_json(cleaned)

    lines = cleaned.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)

    while lines and _is_thinking_prefix(lines[0]):
        lines.pop(0)
        while lines and lines[0].strip() and not _looks_like_answer_boundary(lines[0]):
            lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"(?i)^answer:\s*", "", cleaned).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _strip_tool_call_json(text: str) -> str:
    """Remove tool-call JSON that a model may leak into a user-facing reply.

    Targets both fenced ```json {"name": ...}``` blocks and bare
    {"name": "...", "arguments": {...}} objects. Anything that does not parse to
    an object with a "name" key is left untouched.
    """

    def _looks_like_tool_call(body: str) -> bool:
        # Valid JSON object with a "name" key, OR clearly tool-call-shaped text
        # (Windows-path tool calls often have invalid JSON escapes, so we can't
        # rely on json.loads alone).
        try:
            data = json.loads(body)
            if isinstance(data, dict) and "name" in data:
                return True
        except json.JSONDecodeError:
            pass
        return bool(re.search(r'"name"\s*:', body) and re.search(r'"arguments"\s*:', body))

    def _fenced(match: "re.Match[str]") -> str:
        return "" if _looks_like_tool_call(match.group(1).strip()) else match.group(0)

    text = re.sub(r"```(?:json)?\s*(\{.*?\})\s*```", _fenced, text, flags=re.DOTALL | re.IGNORECASE)

    # Bare object containing "name" and an "arguments" object (one level of nesting).
    text = re.sub(
        r'\{[^{}]*?"name"\s*:\s*"[^"]*"[^{}]*?"arguments"\s*:\s*\{[^{}]*\}\s*\}',
        "",
        text,
        flags=re.DOTALL,
    )
    return text


def _is_thinking_prefix(line: str) -> bool:
    normalized = line.strip().lower()
    return any(normalized.startswith(prefix) for prefix in THINKING_PREFIXES)


def _looks_like_answer_boundary(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.lower().startswith("answer:")
        or stripped.startswith("#")
        or stripped.startswith("- ")
        or bool(re.match(r"^\d+\.\s", stripped))
    )
