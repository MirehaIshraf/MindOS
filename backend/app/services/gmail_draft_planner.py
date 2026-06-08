import json
import re
from collections import defaultdict
from typing import Any

from app.schemas.gmail import GmailDraftPrepareRequest, GmailDraftPrepareResponse, GmailDraftPrepareSourceItem
from app.services.model_router_service import model_router_service


class GmailDraftPlanner:
    def prepare(self, request: GmailDraftPrepareRequest) -> GmailDraftPrepareResponse:
        grouped_facts = self._group_source_facts(request.recent_tasks)
        if not grouped_facts:
            grouped_facts = "No recent task history was provided."

        try:
            result = model_router_service.generate(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You write clean email drafts from user-provided local task history. "
                            "Use only the provided facts. Do not invent work. Do not expose internal event names. "
                            "Do not mention MindOS task activity unless the user explicitly asks. "
                            "Return JSON only with keys: to, subject, body, tone, source_summary."
                        ),
                    },
                    {
                        "role": "user",
                        "content": self._prompt(request, grouped_facts),
                    },
                ],
                requested_model_id=request.model_id,
                options={"temperature": 0.2},
            )
            if result.provider == "fake":
                fallback = self._deterministic_draft(request, grouped_facts)
                fallback.warnings.append("AI drafting was unavailable, so MindOS used a safe basic draft.")
                fallback.model = result.model_used
                fallback.provider = result.provider
                fallback.model_display_name = result.model_display_name
                fallback.planner_warning = result.warning
                return fallback
            parsed = self._parse_json(result.reply)
            subject = str(parsed.get("subject") or "").strip()
            body = str(parsed.get("body") or "").strip()
            if not subject or not body:
                raise ValueError("Draft JSON was missing subject or body.")
            return GmailDraftPrepareResponse(
                to=str(parsed.get("to") or "").strip(),
                subject=subject,
                body=self._clean_body(body),
                tone=str(parsed.get("tone") or "professional").strip() or "professional",
                source_summary=str(parsed.get("source_summary") or self._source_summary(request.recent_tasks)).strip(),
                warnings=[],
                model=result.model_used,
                provider=result.provider,
                model_display_name=result.model_display_name,
                planner_warning=result.warning,
            )
        except Exception:
            fallback = self._deterministic_draft(request, grouped_facts)
            fallback.warnings.append("AI drafting was unavailable, so MindOS used a safe basic draft.")
            return fallback

    def _prompt(self, request: GmailDraftPrepareRequest, grouped_facts: str) -> str:
        return "\n".join(
            [
                f"Request: {request.instruction}",
                f"Connected Gmail account: {request.connected_email or 'unknown'}",
                "",
                "Task history from last 7 days, grouped and deduplicated:",
                grouped_facts,
                "",
                "Relevant memory:",
                self._group_source_facts(request.memory_items) or "No additional memory was provided.",
                "",
                "Return JSON only:",
                '{"to":"","subject":"...","body":"...","tone":"professional","source_summary":"..."}',
                "",
                "Email style:",
                "- professional",
                "- concise",
                "- organized",
                "- human sounding",
                "- no raw internal labels",
                "- do not dump file names or counts unless they are clearly useful",
                "- no fake claims",
                "- if the user asks for Bengali, write Bengali; otherwise write English",
            ]
        )

    def _group_source_facts(self, items: list[GmailDraftPrepareSourceItem]) -> str:
        if not items:
            return ""
        grouped: dict[str, list[GmailDraftPrepareSourceItem]] = defaultdict(list)
        for item in items:
            grouped[self._group_label(item.type)].append(item)

        lines: list[str] = []
        for group, group_items in grouped.items():
            lines.append(f"{group}:")
            if group == "Document summaries":
                output_files = [item.output_file_name for item in group_items if item.output_file_name]
                lines.append(f"- Created {len(group_items)} summary document{'s' if len(group_items) != 1 else ''}.")
                if output_files:
                    lines.append(f"- Files saved: {', '.join(output_files[:8])}.")
            elif group == "File organization":
                moved = sum(self._safe_int(item.details.get("moved_files")) for item in group_items)
                created = sum(self._safe_int(item.details.get("created_folders")) for item in group_items)
                lines.append(f"- Organized {len(group_items)} folder task{'s' if len(group_items) != 1 else ''}.")
                if moved or created:
                    lines.append(f"- Created {created} folders and moved {moved} files.")
            else:
                for item in group_items[:8]:
                    clean = self._clean_fact(f"{item.title}: {item.summary}")
                    if clean:
                        lines.append(f"- {clean}")
            lines.append("")
        return "\n".join(lines).strip()

    def _group_label(self, item_type: str) -> str:
        if item_type == "document_summary":
            return "Document summaries"
        if item_type in {"file_organize", "file_move", "file_copy", "file_rename", "create_folders"}:
            return "File organization"
        if item_type.startswith("github"):
            return "GitHub activity"
        if item_type.startswith("gmail") or item_type.startswith("email"):
            return "Email activity"
        if item_type.startswith("browser"):
            return "Browser and research activity"
        return "Other work"

    def _deterministic_draft(self, request: GmailDraftPrepareRequest, grouped_facts: str) -> GmailDraftPrepareResponse:
        if grouped_facts == "No recent task history was provided.":
            body = (
                "Hi,\n\n"
                "I wanted to share a short update on my work from the last 7 days. "
                "I do not have enough task history available here to list specific completed items, "
                "but I can add more details once the relevant work history is synced.\n\n"
                "Best regards,"
            )
            source_summary = "No recent task history was available."
        else:
            body = (
                "Hi,\n\n"
                "Here is a short summary of my work from the last 7 days:\n\n"
                f"{self._facts_to_email_text(grouped_facts)}\n\n"
                "Please let me know if you need more details.\n\n"
                "Best regards,"
            )
            source_summary = self._source_summary(request.recent_tasks)
        return GmailDraftPrepareResponse(
            to="",
            subject="Summary of my work from the last 7 days",
            body=body,
            tone="professional",
            source_summary=source_summary,
            warnings=[],
        )

    def _facts_to_email_text(self, grouped_facts: str) -> str:
        text = grouped_facts.replace("Document summaries:", "Document summaries").replace("File organization:", "File organization")
        return "\n".join(line for line in text.splitlines() if line.strip())

    def _source_summary(self, items: list[GmailDraftPrepareSourceItem]) -> str:
        count = len(items)
        return f"Used {count} task history item{'s' if count != 1 else ''} from the last 7 days." if count else "No recent task history was available."

    def _parse_json(self, raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("Draft response was not a JSON object.")
        return parsed

    def _clean_body(self, body: str) -> str:
        blocked = ["document_summary", "task_history", "memory event", "source id"]
        lines = [line for line in body.splitlines() if not any(term in line.lower() for term in blocked)]
        return "\n".join(lines).strip()

    def _clean_fact(self, value: str) -> str:
        value = re.sub(r"\b(document_summary|task_history|memory_event|source_id)\b", "", value, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", value).strip(" -:")

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0


gmail_draft_planner = GmailDraftPlanner()
