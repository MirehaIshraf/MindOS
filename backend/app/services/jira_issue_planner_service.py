import json
import re
from typing import Any

from app.schemas.jira import DEFAULT_JIRA_ISSUE_TYPE, JiraIssueDraftRequest, JiraIssueDraftResponse
from app.services.jira_service import jira_service
from app.services.model_router_service import model_router_service


class JiraIssuePlannerService:
    def prepare(self, request: JiraIssueDraftRequest) -> JiraIssueDraftResponse:
        default_project, default_issue_type = self._defaults(request)
        fallback = self._deterministic_draft(request, default_project, default_issue_type)
        try:
            result = model_router_service.generate(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You draft Jira issue previews from user-provided facts. Return JSON only. "
                            "Use only the provided facts. Do not invent stack traces, customers, severity, deadlines, or incidents. "
                            "Separate evidence from hypotheses. Allowed keys: project_key, issue_type, summary, description, labels, priority, search_query."
                        ),
                    },
                    {"role": "user", "content": self._prompt(request, default_project, default_issue_type)},
                ],
                requested_model_id=request.model_id,
                options={"temperature": 0.2},
            )
            if result.provider == "fake":
                fallback.warnings.append("AI Jira drafting was unavailable, so MindOS used a safe basic draft.")
                fallback.model = result.model_used
                fallback.provider = result.provider
                fallback.model_display_name = result.model_display_name
                return fallback
            parsed = self._parse_json(result.reply)
            summary = self._clean_summary(str(parsed.get("summary") or fallback.summary))
            description = self._clean_description(str(parsed.get("description") or fallback.description))
            if not summary or not description:
                raise ValueError("Jira draft JSON was missing summary or description.")
            return JiraIssueDraftResponse(
                project_key=self._clean_project_key(str(parsed.get("project_key") or default_project or "")) or default_project,
                issue_type=str(parsed.get("issue_type") or default_issue_type or DEFAULT_JIRA_ISSUE_TYPE).strip() or DEFAULT_JIRA_ISSUE_TYPE,
                summary=summary,
                description=description,
                labels=self._labels(parsed.get("labels") or fallback.labels),
                priority=str(parsed.get("priority") or "").strip() or None,
                search_query=self._clean_summary(str(parsed.get("search_query") or fallback.search_query)),
                warnings=[],
                model=result.model_used,
                provider=result.provider,
                model_display_name=result.model_display_name,
            )
        except Exception:
            fallback.warnings.append("AI Jira drafting failed, so MindOS used a safe basic draft.")
            return fallback

    def _prompt(self, request: JiraIssueDraftRequest, default_project: str | None, default_issue_type: str) -> str:
        existing = [
            {
                "key": issue.key,
                "summary": issue.summary,
                "status": issue.status,
                "issue_type": issue.issue_type,
                "url": issue.url,
            }
            for issue in request.existing_issues[:10]
        ]
        payload = {
            "instruction": request.instruction,
            "default_project_key": default_project,
            "default_issue_type": default_issue_type,
            "context_summary": request.context_summary,
            "selected_filenames": request.selected_filenames[:10],
            "similar_existing_issues": existing,
            "rules": [
                "Use only provided facts.",
                "Include problem summary, evidence, hypothesis, and suggested next steps when useful.",
                "Keep summary concise.",
                "Do not claim severity, customers, stack traces, or deadlines unless provided.",
                "Return JSON only.",
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _deterministic_draft(self, request: JiraIssueDraftRequest, default_project: str | None, default_issue_type: str) -> JiraIssueDraftResponse:
        summary = self._clean_summary(request.instruction)
        summary = re.sub(r"\b(create|make|open|draft|prepare)\b\s+(a\s+)?\b(jira|ticket|issue|task|bug)\b\s*(for|about)?", "", summary, flags=re.IGNORECASE)
        summary = re.sub(r"\s+", " ", summary).strip(" .:-") or "MindOS generated Jira issue"
        issue_type = request.issue_type or ("Bug" if re.search(r"\b(error|bug|failed|failure|exception|crash|timeout)\b", request.instruction, re.IGNORECASE) else default_issue_type)
        evidence = request.context_summary or "User request: " + request.instruction
        if request.selected_filenames:
            evidence += "\nSelected source files: " + ", ".join(request.selected_filenames[:10])
        if request.existing_issues:
            evidence += "\nSimilar existing issues were found; review before creating a duplicate."
        description = "\n".join(
            [
                "Problem summary",
                summary,
                "",
                "Evidence",
                evidence,
                "",
                "Hypothesis",
                "Needs investigation. No unverified root cause is assumed.",
                "",
                "Suggested next steps",
                "- Review the evidence.",
                "- Reproduce the issue if possible.",
                "- Add implementation details after triage.",
            ]
        )
        return JiraIssueDraftResponse(
            project_key=request.project_key or default_project,
            issue_type=issue_type or DEFAULT_JIRA_ISSUE_TYPE,
            summary=summary[:180],
            description=description,
            labels=["mindos"],
            priority=None,
            search_query=self._search_query(request.instruction),
            warnings=[],
        )

    def _defaults(self, request: JiraIssueDraftRequest) -> tuple[str | None, str]:
        status = jira_service.status()
        return request.project_key or status.default_project_key, request.issue_type or status.default_issue_type or DEFAULT_JIRA_ISSUE_TYPE

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
            raise ValueError("Jira draft response was not a JSON object.")
        return parsed

    def _clean_summary(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())[:180]

    def _clean_description(self, value: str) -> str:
        return value.strip()[:12000]

    def _clean_project_key(self, value: str) -> str | None:
        cleaned = "".join(char for char in value.upper().strip() if char.isalnum() or char == "_")
        return cleaned or None

    def _labels(self, value: Any) -> list[str]:
        labels = value if isinstance(value, list) else []
        cleaned: list[str] = []
        for label in labels:
            safe = re.sub(r"[^A-Za-z0-9_-]+", "-", str(label).strip()).strip("-")
            if safe:
                cleaned.append(safe[:50])
        return list(dict.fromkeys(cleaned))[:10] or ["mindos"]

    def _search_query(self, instruction: str) -> str:
        cleaned = re.sub(r"\b(create|make|open|draft|prepare|jira|ticket|issue|task|bug|check|already|exists|there|is|about|for)\b", " ", instruction, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cleaned).strip()[:120] or instruction.strip()[:120] or "issue"


jira_issue_planner_service = JiraIssuePlannerService()
