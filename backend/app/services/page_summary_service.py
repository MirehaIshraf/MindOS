import re


def create_deterministic_summary(
    title: str,
    url: str,
    headings: list[str] | None,
    text_excerpt: str,
    max_summary_chars: int = 1200,
) -> dict:
    headings = [heading.strip() for heading in (headings or []) if heading.strip()][:8]
    clean_text = _clean_text(text_excerpt)
    if not clean_text:
        return {
            "summary": "Readable page context was not captured.",
            "key_points": [],
            "headings": headings,
            "summary_status": "not_required",
            "summary_method": None,
        }
    paragraphs = [part.strip() for part in re.split(r"\n{2,}|(?<=\.)\s+", clean_text) if len(part.strip()) > 40]
    summary = " ".join(paragraphs[:3]).strip()
    if len(summary) > max_summary_chars:
        summary = f"{summary[:max_summary_chars].rsplit(' ', 1)[0]}..."
    key_points = headings[:5] or _key_terms(title, clean_text)[:5]
    return {
        "summary": summary,
        "key_points": key_points,
        "headings": headings,
        "summary_status": "ready" if should_summarize_immediately(clean_text, headings) else "pending",
        "summary_method": "deterministic" if should_summarize_immediately(clean_text, headings) else None,
    }


def should_summarize_immediately(text_excerpt: str, headings: list[str] | None = None) -> bool:
    return 0 < len(_clean_text(text_excerpt)) <= 2500


def extract_readable_context(content: str) -> str:
    marker = "Readable context excerpt:"
    if marker.lower() in content.lower():
        _, tail = content.lower().split(marker.lower(), 1)
        start = len(content) - len(tail)
        excerpt = content[start:].strip()
        selected_index = excerpt.lower().find("\n\nselected text:")
        if selected_index >= 0:
            excerpt = excerpt[:selected_index].strip()
        return excerpt
    marker = "Context excerpt:"
    if marker.lower() in content.lower():
        _, tail = content.lower().split(marker.lower(), 1)
        start = len(content) - len(tail)
        return content[start:].strip()
    return ""


def extract_headings(content: str) -> list[str]:
    marker = "Headings:"
    if marker.lower() not in content.lower():
        return []
    _, tail = content.lower().split(marker.lower(), 1)
    start = len(content) - len(tail)
    heading_block = content[start:].split("\n\n", 1)[0]
    return [line.strip("- ").strip() for line in heading_block.splitlines() if line.strip().startswith("-")]


def format_browser_capture_content(
    *,
    title: str,
    url: str,
    domain: str,
    page_type: str,
    category: str,
    summary_result: dict,
    readable_context: str,
) -> str:
    summary_status = summary_result.get("summary_status")
    summary = summary_result.get("summary") or "Summary pending. Readable page context was captured."
    if summary_status == "pending":
        summary = "Summary pending. Readable page context was captured."
    key_points = summary_result.get("key_points") or []
    return "\n\n".join(
        part
        for part in [
            f"Page: {title}",
            f"URL: {url}",
            f"Domain: {domain}",
            f"Page type: {page_type}",
            f"Category: {category}",
            f"Summary:\n{summary}",
            "Key points:\n" + "\n".join(f"- {point}" for point in key_points) if key_points else "",
            f"Readable context excerpt:\n{readable_context}" if readable_context else "Readable page context was not captured.",
        ]
        if part
    )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _key_terms(title: str, text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", f"{title} {text[:1000]}")
    stop = {"this", "that", "with", "from", "page", "data", "more", "about", "using"}
    terms: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered not in stop and lowered not in [term.lower() for term in terms]:
            terms.append(word)
    return terms
