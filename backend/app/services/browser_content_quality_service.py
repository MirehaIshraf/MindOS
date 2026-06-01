from __future__ import annotations

import re
from typing import Any


PLACEHOLDER_PHRASES = [
    "No readable page text was extracted.",
    "Readable page context was not captured.",
    "No readable page context was captured.",
    "Could not extract page text.",
    "Page context missing.",
]


def extracted_text_from_content(content: str | None) -> str:
    if not content:
        return ""
    markers = [
        "Readable context excerpt:",
        "Context excerpt:",
    ]
    lowered = content.lower()
    for marker in markers:
        marker_lower = marker.lower()
        if marker_lower in lowered:
            start = lowered.find(marker_lower) + len(marker)
            excerpt = content[start:].strip()
            for next_label in ["\n\nSelected text:", "\n\nMetadata:", "\n\nURL:", "\n\nDomain:"]:
                next_index = excerpt.lower().find(next_label.lower())
                if next_index >= 0:
                    excerpt = excerpt[:next_index].strip()
            return clean_extracted_text(excerpt)
    return clean_extracted_text(content)


def clean_extracted_text(text: str | None) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    for phrase in PLACEHOLDER_PHRASES:
        value = value.replace(phrase, "").strip()
    value = re.sub(r"^(Readable context excerpt|Context excerpt):\s*", "", value, flags=re.IGNORECASE).strip()
    return value


def is_meaningful_extracted_text(text: str | None, metadata: dict[str, Any] | None = None) -> bool:
    metadata = metadata or {}
    structured_fields = metadata.get("structured_fields")
    if isinstance(structured_fields, list) and structured_fields:
        return True
    structured = metadata.get("structured")
    if isinstance(structured, dict) and any(bool(value) for value in structured.values()):
        return True
    cleaned = clean_extracted_text(text)
    if not cleaned:
        return False
    lines = [line.strip() for line in re.split(r"[\n\r]+", text or "") if clean_extracted_text(line)]
    return len(cleaned) >= 120 or len(lines) >= 3


def content_quality_from_capture(content: str | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    extracted_text = extracted_text_from_content(content)
    meaningful = is_meaningful_extracted_text(extracted_text, metadata)
    if not meaningful:
        return {
            "meaningful": False,
            "captured_text_chars": 0,
            "text_excerpt_included": False,
            "page_context_missing": True,
            "content_quality": "title_only",
            "summary_status": "not_required",
            "summary_method": None,
            "extracted_text": "",
        }
    return {
        "meaningful": True,
        "captured_text_chars": len(extracted_text),
        "text_excerpt_included": True,
        "page_context_missing": False,
        "content_quality": "excerpt",
        "summary_status": "pending",
        "summary_method": None,
        "extracted_text": extracted_text,
    }
