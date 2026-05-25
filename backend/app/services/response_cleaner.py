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
