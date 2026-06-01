import re

from app.domain.models import Event


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


def create_deterministic_page_summary(event: Event, max_summary_chars: int = 1200) -> dict:
    metadata = event.metadata or {}
    title = str(metadata.get("page_title") or event.title)
    url = str(metadata.get("url") or "")
    domain = str(metadata.get("domain") or "")
    headings = [str(heading).strip() for heading in metadata.get("headings", []) if str(heading).strip()][:10]
    meta_description = str(metadata.get("meta_description") or "").strip()
    readable_context = clean_page_text(extract_readable_context(event.content))
    if not readable_context:
        return {
            "summary": "Readable page context was not captured.",
            "key_points": [],
            "headings": headings,
            "summary_status": "not_required",
            "summary_method": None,
            "readable_context": "",
        }

    paragraphs = _meaningful_paragraphs(readable_context)
    summary_parts = [part for part in [meta_description, *paragraphs[:3]] if part]
    summary = " ".join(summary_parts).strip()
    if len(summary) > max_summary_chars:
        summary = f"{summary[:max_summary_chars].rsplit(' ', 1)[0]}..."
    key_points = _key_points_for_page(title=title, text=readable_context, headings=headings, metadata=metadata)
    return {
        "summary": summary,
        "key_points": key_points,
        "headings": headings,
        "summary_status": "ready",
        "summary_method": "deterministic",
        "source_url": url,
        "domain": domain,
        "readable_context": readable_context,
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


def clean_page_text(value: str) -> str:
    lines = []
    for line in re.split(r"[\n\r]+|(?<=\.)\s+", value or ""):
        cleaned = _clean_text(line)
        if not cleaned or _is_navigation_noise(cleaned):
            continue
        lines.append(cleaned)
    collapsed: list[str] = []
    for line in lines:
        if collapsed and collapsed[-1].lower() == line.lower():
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip()


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


def format_summarized_browser_capture_content(event: Event, summary_result: dict) -> str:
    metadata = event.metadata or {}
    title = str(metadata.get("page_title") or event.title)
    url = str(metadata.get("url") or summary_result.get("source_url") or "")
    domain = str(metadata.get("domain") or summary_result.get("domain") or "")
    page_type = str(metadata.get("page_type") or "content")
    category = str(metadata.get("category") or "browser")
    readable_context = str(summary_result.get("readable_context") or clean_page_text(extract_readable_context(event.content)))
    key_points = [str(point) for point in summary_result.get("key_points", []) if str(point).strip()]
    parts = [
        f"Page: {title}",
        f"URL: {url}" if url else "",
        f"Domain: {domain}" if domain else "",
        f"Page type: {page_type}",
        f"Category: {category}",
        f"Summary:\n{summary_result.get('summary') or 'Readable page context was not captured.'}",
        "Key points:\n" + "\n".join(f"- {point}" for point in key_points) if key_points else "",
        f"Readable context excerpt:\n{readable_context}" if readable_context else "Readable page context was not captured.",
    ]
    return "\n\n".join(part for part in parts if part)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _meaningful_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n+|(?<=\.)\s+", text) if len(part.strip()) > 45 and not _is_navigation_noise(part)]


def _is_navigation_noise(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip().lower()
    noisy = {
        "models",
        "datasets",
        "spaces",
        "buckets",
        "pricing",
        "website",
        "tasks",
        "huggingchat",
        "collections",
        "organizations",
        "community",
        "blog",
        "docs",
        "log in",
        "sign up",
        "follow",
        "like",
    }
    return normalized in noisy or (len(normalized) < 4 and normalized not in {"ai"})


def _key_points_for_page(title: str, text: str, headings: list[str], metadata: dict) -> list[str]:
    category = str(metadata.get("category") or "")
    url = str(metadata.get("url") or "")
    points: list[str] = []
    if "huggingface.co" in url:
        model_or_dataset = _huggingface_name(url) or title
        if model_or_dataset:
            label = "dataset" if "dataset" in category or "/datasets/" in url else "model"
            points.append(f"Hugging Face {label}: {model_or_dataset}")
    points.extend(heading for heading in headings if heading not in points)
    if len(points) < 3:
        points.extend(_key_terms(title, text))
    deduped: list[str] = []
    for point in points:
        clean = _clean_text(point)
        if clean and clean.lower() not in {item.lower() for item in deduped}:
            deduped.append(clean)
    return deduped[:6]


def _huggingface_name(url: str) -> str:
    match = re.search(r"huggingface\.co/(?:models/|datasets/|spaces/)?([^?#]+)", url)
    return match.group(1).strip("/") if match else ""


def _key_terms(title: str, text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", f"{title} {text[:1000]}")
    stop = {"this", "that", "with", "from", "page", "data", "more", "about", "using"}
    terms: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered not in stop and lowered not in [term.lower() for term in terms]:
            terms.append(word)
    return terms
