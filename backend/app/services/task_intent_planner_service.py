import json
import re
from typing import Any

from app.schemas.task_actions import (
    TaskIntentEntities,
    TaskIntentPlanStep,
    TaskIntentPrepareRequest,
    TaskIntentPrepareResponse,
)
from app.services.model_router_service import model_router_service


ALLOWED_STEP_TYPES = {
    "file.search_connected_folders",
    "file.select_candidates",
    "document.summarize_selected_files",
    "document.create_report_from_files",
    "document.create_output_file",
    "log.search_connected_logs",
    "log.analyze_selected_files",
    "gmail.create_draft",
    "gmail.send_email_after_confirmation",
    "gmail.attach_selected_files",
    "task.ask_user_to_choose_files",
    "unsupported",
}
ALLOWED_ACTIONS = {
    "file.search",
    "file.organize",
    "document.summaryFromSearch",
    "document.reportFromSearch",
    "log.analyzeFromSearch",
    "gmail.createDraft",
    "gmail.sendEmail",
    "gmail.sendGeneratedReport",
    "multi_step",
    "unsupported",
}
LOG_EXTENSIONS = [".log", ".txt", ".out", ".err"]
LOG_KEYWORDS = ["log", "error", "app", "server", "backend", "frontend", "api", "debug", "trace", "exception"]


class TaskIntentPlannerService:
    def prepare(self, request: TaskIntentPrepareRequest) -> TaskIntentPrepareResponse:
        hints = self._preparse(request.instruction)
        if request.use_llm_planner:
            try:
                result = model_router_service.generate(
                    messages=[
                        {"role": "system", "content": self._system_prompt()},
                        {"role": "user", "content": self._prompt(request.instruction, hints)},
                    ],
                    requested_model_id=request.model_id,
                    options={"temperature": 0.1},
                )
                if result.provider != "fake":
                    parsed = self._parse_json(result.reply)
                    planned = self._response_from_json(parsed)
                    planned.planner_method = "llm"
                    return self._validate_and_normalize(planned, request.instruction, hints)
            except Exception as error:
                fallback = self._deterministic_plan(request.instruction, hints, planner_method="fallback")
                fallback.warnings.append(f"AI task planner failed; using deterministic fallback. {error}")
                return fallback

        fallback = self._deterministic_plan(request.instruction, hints, planner_method="fallback" if request.use_llm_planner else "deterministic")
        if request.use_llm_planner:
            fallback.warnings.append("AI task planner unavailable; using deterministic fallback.")
        return fallback

    def _system_prompt(self) -> str:
        return (
            "You are MindOS task planner. You classify user requests into safe task plans. "
            "Return JSON only. Do not execute. Do not invent available files. Use deterministic hints, "
            "but override them when user meaning is clear. Prefer multi-step plans for real tasks. "
            "If the task needs files, search connected folders first. If file choice is ambiguous, require user selection. "
            "If the user asks to summarize, analyze, or report, do not classify as file organization. "
            "If the user asks to organize, move, clean, sort, rename, or copy files, classify as file organization. "
            "Side-effect actions require preview and confirmation. Available step types: "
            "file.search_connected_folders, file.select_candidates, document.summarize_selected_files, "
            "document.create_report_from_files, document.create_output_file, log.search_connected_logs, "
            "log.analyze_selected_files, gmail.create_draft, gmail.send_email_after_confirmation, "
            "gmail.attach_selected_files, task.ask_user_to_choose_files, unsupported. "
            "Available high-level action types: file.search, file.organize, document.summaryFromSearch, "
            "document.reportFromSearch, log.analyzeFromSearch, gmail.createDraft, gmail.sendEmail, gmail.sendGeneratedReport, multi_step, unsupported. "
            "Rules: 'summarize errors from the log files' means log.analyzeFromSearch. "
            "'create a summarization from the files of plan 2026' means document.summaryFromSearch. "
            "'find my resume and draft/send email' means file search first, then Gmail. "
            "Do not classify summarization/report requests as organize folder. Do not select files silently if multiple files match. "
            "Do not use task history unless the request asks about recent work/tasks. Use connected file index for files, not live full PC scan. "
            "Use Gmail connector for Gmail tasks, not Email MCP. If no matching files are found, ask user to choose files."
        )

    def _preparse(self, instruction: str) -> dict[str, Any]:
        text = instruction.lower()
        emails = [match[0] or match[1] for match in re.findall(r"\[([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\]\(mailto:[^)]+\)|([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", instruction, flags=re.IGNORECASE)]
        explicit_file_names = self._explicit_file_names(instruction)
        action_words = self._matched_words(text, ["summarize", "summary", "summarization", "report", "analyze", "analyse", "find", "search", "create", "draft", "send", "organize", "move", "sort", "clean", "rename", "copy"])
        connector_words = self._matched_words(text, ["gmail", "email", "mail", "log", "logs", "log files", "github", "task history", "connected folders"])
        attachment_words = self._matched_words(text, ["attach", "attachment", "resume", "cv", "file", "files", "document", "documents"])
        output_words = self._matched_words(text, ["summary", "summarization", "report", "output", "document", "file"])
        risk_words = self._matched_words(text, ["send", "delete", "remove", "overwrite", "move", "rename", "copy"])
        extensions = self._extensions(instruction)
        possible_intents = self._possible_intents(text, extensions, emails)
        topic_terms = self._topic_terms(instruction, action_words, connector_words)
        file_terms = self._file_terms(instruction, explicit_file_names, topic_terms)
        wants_draft = bool(re.search(r"\b(draft|compose|write|create a draft)\b", text))
        explicit_send = bool(re.search(r"\b(send|email|mail)\b", text)) and not wants_draft
        return {
            "emails": emails,
            "date_ranges": self._date_ranges(text),
            "file_terms": file_terms,
            "topic_terms": topic_terms,
            "explicit_file_names": explicit_file_names,
            "extensions": extensions,
            "action_words": action_words,
            "connector_words": connector_words,
            "attachment_words": attachment_words,
            "output_words": output_words,
            "risk_words": risk_words,
            "possible_intents": possible_intents,
            "has_mail_words": bool(re.search(r"\b(gmail|email|mail)\b", text) or emails),
            "has_file_search_words": bool(file_terms or explicit_file_names or re.search(r"\b(find|search|look up|lookup|attach|attachment|files?|documents?)\b", text)),
            "has_attachment_intent": bool(attachment_words and (emails or re.search(r"\b(send|mail|email|draft|attach|attachment)\b", text))),
            "wants_draft": wants_draft,
            "wants_send": explicit_send,
            "wants_summary": self._is_summary_request(text),
            "wants_log_analysis": self._is_log_analysis(text),
            "wants_organize": self._is_organize_request(text),
            "latest_preference": bool(re.search(r"\b(latest|recent|newest|last)\b", text)),
            "exact_file_hint": self._exact_file_hint(instruction),
        }

    def _deterministic_plan(self, instruction: str, hints: dict[str, Any], *, planner_method: str) -> TaskIntentPrepareResponse:
        recipients = list(hints.get("emails") or [])
        wants_mail = bool(hints.get("has_mail_words"))
        wants_draft = bool(hints.get("wants_draft"))
        wants_send = bool(hints.get("wants_send")) and not wants_draft
        wants_file = bool(hints.get("has_file_search_words"))

        if hints.get("wants_log_analysis") and wants_mail:
            return self._log_then_gmail_plan(instruction, hints, recipients, wants_send, planner_method)
        if hints.get("wants_log_analysis"):
            return self._log_plan(instruction, hints, planner_method)
        if hints.get("wants_summary") and (wants_file or re.search(r"\b(files?|documents?|docs?)\b", instruction, flags=re.IGNORECASE)):
            if wants_mail:
                return self._summary_then_gmail_plan(instruction, hints, recipients, wants_send, planner_method)
            return self._document_summary_plan(instruction, hints, planner_method)
        if wants_file and wants_mail:
            return self._file_then_gmail_plan(instruction, hints, recipients, wants_send, wants_draft, planner_method)
        if hints.get("wants_organize"):
            return self._organize_plan(instruction, hints, planner_method)
        return self._unsupported_plan("I need a clearer supported task before preparing a preview.", hints, planner_method)

    def _validate_and_normalize(self, planned: TaskIntentPrepareResponse, instruction: str, hints: dict[str, Any]) -> TaskIntentPrepareResponse:
        repairs: list[str] = []
        if planned.primary_action not in ALLOWED_ACTIONS:
            repairs.append(f"Unsupported action '{planned.primary_action}' was replaced.")
            planned = self._deterministic_plan(instruction, hints, planner_method="fallback")
        if planned.confidence < 0.55 and planned.confidence > 0:
            planned.primary_action = "unsupported"
            planned.intent = "unsupported"
            planned.source_type = "none"
            planned.steps = [TaskIntentPlanStep(id="step_1", type="task.ask_user_to_choose_files", purpose="Clarify task action")]
            planned.explanation = "I am not fully sure what you want to do."
            planned.user_facing_summary = "Choose whether to search files, analyze logs, organize a folder, or draft Gmail."
            planned.validation_repairs = repairs
            return planned

        if hints.get("wants_summary") and planned.primary_action == "file.organize":
            repairs.append("Summary/report request was repaired from file organization to document summary.")
            planned = self._document_summary_plan(instruction, hints, "fallback")
        if hints.get("wants_log_analysis") and planned.primary_action != "log.analyzeFromSearch":
            repairs.append("Log analysis request was repaired to log analysis.")
            planned = self._log_plan(instruction, hints, "fallback")

        planned.steps = [step for step in planned.steps if step.type in ALLOWED_STEP_TYPES]
        if not planned.steps:
            repaired = self._deterministic_plan(instruction, hints, planner_method="fallback")
            repaired.validation_repairs = repairs + ["Planner returned no allowed steps; fallback used."]
            return repaired

        if planned.primary_action == "document.summaryFromSearch":
            self._ensure_document_summary_steps(planned, instruction, hints, repairs)
        elif planned.primary_action == "document.reportFromSearch":
            self._ensure_document_summary_steps(planned, instruction, hints, repairs, report=True)
        elif planned.primary_action == "log.analyzeFromSearch":
            self._ensure_log_steps(planned, instruction, hints, repairs)
        elif planned.primary_action in {"gmail.createDraft", "gmail.sendEmail", "gmail.sendGeneratedReport", "multi_step"}:
            self._ensure_gmail_steps(planned, instruction, hints, repairs)
        elif planned.primary_action == "file.organize" and not hints.get("wants_organize"):
            repaired = self._unsupported_plan("This does not look like a file organization request.", hints, "fallback")
            repaired.validation_repairs = repairs + ["Blocked file organization without explicit organize/move/sort/clean intent."]
            return repaired

        for step in planned.steps:
            if step.type in {"file.search_connected_folders", "log.search_connected_logs"}:
                step.requires_user_selection = True
            if step.type == "gmail.send_email_after_confirmation":
                step.requires_confirmation = True
        planned.requires_confirmation = True
        planned.validation_repairs = repairs
        if not planned.user_facing_summary:
            planned.user_facing_summary = planned.explanation
        return planned

    def _ensure_document_summary_steps(self, plan: TaskIntentPrepareResponse, instruction: str, hints: dict[str, Any], repairs: list[str], *, report: bool = False) -> None:
        query = self._file_query(instruction, hints)
        if not any(step.type == "file.search_connected_folders" for step in plan.steps):
            plan.steps.insert(0, TaskIntentPlanStep(id="step_search", type="file.search_connected_folders", query=query, requires_user_selection=True))
            repairs.append("Added connected file search before document summary.")
        if not any(step.type == "file.select_candidates" for step in plan.steps):
            plan.steps.insert(1, TaskIntentPlanStep(id="step_select", type="file.select_candidates", requires_user_selection=True))
            repairs.append("Added user file selection before document summary.")
        summary_type = "document.create_report_from_files" if report else "document.summarize_selected_files"
        if not any(step.type in {"document.summarize_selected_files", "document.create_report_from_files"} for step in plan.steps):
            plan.steps.append(TaskIntentPlanStep(id="step_summary", type=summary_type, query=query, files_from_step="step_select", requires_confirmation=True))
            repairs.append("Added selected-file summary/report step.")
        plan.intent = "multi_step"
        plan.source_type = "connected_files"
        plan.needs_file_search = True
        plan.needs_user_file_selection = True
        plan.needs_output_file = True
        plan.entities.file_queries = plan.entities.file_queries or [query]
        plan.entities.topic_queries = plan.entities.topic_queries or [query]

    def _ensure_log_steps(self, plan: TaskIntentPrepareResponse, instruction: str, hints: dict[str, Any], repairs: list[str]) -> None:
        query = self._log_query(instruction, hints)
        search_step = next((step for step in plan.steps if step.type in {"log.search_connected_logs", "file.search_connected_folders"}), None)
        if search_step is None:
            plan.steps.insert(0, TaskIntentPlanStep(id="step_search", type="log.search_connected_logs", query=query, extensions=LOG_EXTENSIONS, requires_user_selection=True))
            repairs.append("Added connected log search step.")
        else:
            search_step.type = "log.search_connected_logs"
            search_step.query = search_step.query or query
            search_step.extensions = LOG_EXTENSIONS
            search_step.requires_user_selection = True
        if not any(step.type == "file.select_candidates" for step in plan.steps):
            plan.steps.insert(1, TaskIntentPlanStep(id="step_select", type="file.select_candidates", requires_user_selection=True))
            repairs.append("Added user log selection step.")
        if not any(step.type == "log.analyze_selected_files" for step in plan.steps):
            plan.steps.append(TaskIntentPlanStep(id="step_analyze", type="log.analyze_selected_files", query=query, files_from_step="step_select", requires_confirmation=True))
            repairs.append("Added selected-log analysis step.")
        if not any(step.type == "document.create_output_file" for step in plan.steps):
            plan.steps.append(TaskIntentPlanStep(id="step_output", type="document.create_output_file", output_format="markdown", filename_hint=self._log_filename_hint(query), requires_confirmation=True))
        plan.intent = "multi_step"
        plan.source_type = "connected_logs"
        plan.needs_file_search = True
        plan.needs_user_file_selection = True
        plan.needs_output_file = True
        plan.entities.extensions = LOG_EXTENSIONS
        plan.entities.latest_preference = bool(hints.get("latest_preference"))
        plan.entities.exact_file_hint = str(hints.get("exact_file_hint") or "") or None
        plan.entities.file_queries = plan.entities.file_queries or [query]
        plan.entities.topic_queries = plan.entities.topic_queries or [query]

    def _ensure_gmail_steps(self, plan: TaskIntentPrepareResponse, instruction: str, hints: dict[str, Any], repairs: list[str]) -> None:
        has_attachment = any(step.attachments_from_step for step in plan.steps) or bool(hints.get("has_attachment_intent"))
        if has_attachment and not any(step.type == "file.search_connected_folders" for step in plan.steps):
            query = self._file_query(instruction, hints)
            plan.steps.insert(0, TaskIntentPlanStep(id="step_search", type="file.search_connected_folders", query=query, requires_user_selection=True))
            repairs.append("Added file search before Gmail attachment step.")
        if has_attachment and not any(step.type == "file.select_candidates" for step in plan.steps):
            plan.steps.insert(1, TaskIntentPlanStep(id="step_select", type="file.select_candidates", requires_user_selection=True))
            repairs.append("Added user file selection before Gmail.")
        for step in plan.steps:
            if step.type in {"gmail.create_draft", "gmail.send_email_after_confirmation"} and has_attachment and not step.attachments_from_step:
                step.attachments_from_step = "step_select"
        plan.source_type = "connected_files" if has_attachment else "gmail"
        plan.needs_file_search = has_attachment
        plan.needs_user_file_selection = has_attachment

    def _response_from_json(self, value: dict[str, Any]) -> TaskIntentPrepareResponse:
        entities = value.get("entities") if isinstance(value.get("entities"), dict) else {}
        steps = []
        for index, item in enumerate(value.get("steps") or []):
            if not isinstance(item, dict):
                continue
            steps.append(
                TaskIntentPlanStep(
                    id=str(item.get("id") or f"step_{index + 1}"),
                    type=self._safe_step_type(str(item.get("type") or "unsupported")),
                    query=str(item.get("query") or "").strip() or None,
                    purpose=str(item.get("purpose") or "").strip() or None,
                    requires_user_selection=bool(item.get("requires_user_selection")),
                    requires_confirmation=bool(item.get("requires_confirmation")),
                    to=[str(email).strip() for email in item.get("to") or [] if str(email).strip()],
                    subject_hint=str(item.get("subject_hint") or "").strip() or None,
                    body_hint=str(item.get("body_hint") or "").strip() or None,
                    attachments_from_step=str(item.get("attachments_from_step") or "").strip() or None,
                    files_from_step=str(item.get("files_from_step") or "").strip() or None,
                    extensions=[self._normalize_extension(extension) for extension in item.get("extensions") or [] if str(extension).strip()],
                    latest_preference=bool(item.get("latest_preference")),
                    exact_file_hint=str(item.get("exact_file_hint") or "").strip() or None,
                    output_format=str(item.get("output_format") or "").strip() or None,
                    filename_hint=str(item.get("filename_hint") or "").strip() or None,
                )
            )
        return TaskIntentPrepareResponse(
            intent=str(value.get("intent") or "unsupported"),  # type: ignore[arg-type]
            primary_action=str(value.get("primary_action") or "unsupported"),
            risk_level=str(value.get("risk_level") or "medium"),  # type: ignore[arg-type]
            requires_user_selection=bool(value.get("requires_user_selection")),
            requires_confirmation=bool(value.get("requires_confirmation", True)),
            confidence=float(value.get("confidence") or 0.0),
            source_type=str(value.get("source_type") or "none"),
            needs_file_search=bool(value.get("needs_file_search")),
            needs_user_file_selection=bool(value.get("needs_user_file_selection")),
            needs_output_file=bool(value.get("needs_output_file")),
            entities=self._entities_from_dict(entities),
            steps=steps,
            explanation=str(value.get("explanation") or value.get("user_facing_summary") or "").strip(),
            user_facing_summary=str(value.get("user_facing_summary") or value.get("explanation") or "").strip(),
            planner_method="llm",
        )

    def _entities_from_dict(self, entities: dict[str, Any]) -> TaskIntentEntities:
        return TaskIntentEntities(
            recipients=[str(email).strip() for email in entities.get("recipients") or [] if str(email).strip()],
            file_queries=[str(query).strip() for query in entities.get("file_queries") or [] if str(query).strip()],
            topic_queries=[str(query).strip() for query in entities.get("topic_queries") or [] if str(query).strip()],
            explicit_file_names=[str(name).strip() for name in entities.get("explicit_file_names") or [] if str(name).strip()],
            action_words=[str(word).strip() for word in entities.get("action_words") or [] if str(word).strip()],
            connector_words=[str(word).strip() for word in entities.get("connector_words") or [] if str(word).strip()],
            attachment_words=[str(word).strip() for word in entities.get("attachment_words") or [] if str(word).strip()],
            output_words=[str(word).strip() for word in entities.get("output_words") or [] if str(word).strip()],
            risk_words=[str(word).strip() for word in entities.get("risk_words") or [] if str(word).strip()],
            date_range=str(entities.get("date_range") or "").strip() or None,
            output_format=str(entities.get("output_format") or "").strip() or None,
            extensions=[self._normalize_extension(extension) for extension in entities.get("extensions") or [] if str(extension).strip()],
            latest_preference=bool(entities.get("latest_preference")),
            exact_file_hint=str(entities.get("exact_file_hint") or "").strip() or None,
            possible_intents=[str(intent).strip() for intent in entities.get("possible_intents") or [] if str(intent).strip()],
        )

    def _prompt(self, instruction: str, hints: dict[str, Any]) -> str:
        schema = {
            "intent": "single_step|multi_step|unsupported",
            "primary_action": "document.summaryFromSearch",
            "confidence": 0.82,
            "source_type": "connected_files|connected_logs|task_history|gmail|github|manual_files|none",
            "needs_file_search": True,
            "needs_user_file_selection": True,
            "needs_output_file": True,
            "requires_confirmation": True,
            "entities": {
                "recipients": [],
                "file_queries": ["plan 2026"],
                "topic_queries": ["plan 2026"],
                "explicit_file_names": [],
                "extensions": [],
                "date_range": None,
                "output_format": "markdown",
            },
            "steps": [{"id": "step_1", "type": "file.search_connected_folders", "query": "plan 2026", "extensions": [], "requires_user_selection": True}],
            "user_facing_summary": "Search connected folders for files related to plan 2026, then summarize selected files.",
        }
        return f"User instruction:\n{instruction}\n\nDeterministic hints:\n{json.dumps(hints)}\n\nReturn JSON only matching this shape:\n{json.dumps(schema)}"

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
            raise ValueError("Planner response was not a JSON object.")
        return parsed

    def _plan(self, *, intent: str, primary_action: str, risk_level: str, requires_user_selection: bool, requires_confirmation: bool, source_type: str, needs_file_search: bool, needs_user_file_selection: bool, needs_output_file: bool, entities: TaskIntentEntities, steps: list[TaskIntentPlanStep], explanation: str, planner_method: str, confidence: float = 0.78) -> TaskIntentPrepareResponse:
        return TaskIntentPrepareResponse(
            intent=intent,  # type: ignore[arg-type]
            primary_action=primary_action,
            risk_level=risk_level,  # type: ignore[arg-type]
            requires_user_selection=requires_user_selection,
            requires_confirmation=requires_confirmation,
            confidence=confidence,
            source_type=source_type,
            needs_file_search=needs_file_search,
            needs_user_file_selection=needs_user_file_selection,
            needs_output_file=needs_output_file,
            entities=entities,
            steps=steps,
            explanation=explanation,
            user_facing_summary=explanation,
            planner_method=planner_method,  # type: ignore[arg-type]
        )

    def _base_entities(self, hints: dict[str, Any], *, file_queries: list[str] | None = None, topic_queries: list[str] | None = None, extensions: list[str] | None = None) -> TaskIntentEntities:
        return TaskIntentEntities(
            recipients=list(hints.get("emails") or []),
            file_queries=file_queries or list(hints.get("file_terms") or []),
            topic_queries=topic_queries or list(hints.get("topic_terms") or []),
            explicit_file_names=list(hints.get("explicit_file_names") or []),
            action_words=list(hints.get("action_words") or []),
            connector_words=list(hints.get("connector_words") or []),
            attachment_words=list(hints.get("attachment_words") or []),
            output_words=list(hints.get("output_words") or []),
            risk_words=list(hints.get("risk_words") or []),
            extensions=extensions or list(hints.get("extensions") or []),
            latest_preference=bool(hints.get("latest_preference")),
            exact_file_hint=str(hints.get("exact_file_hint") or "") or None,
            possible_intents=list(hints.get("possible_intents") or []),
        )

    def _document_summary_plan(self, instruction: str, hints: dict[str, Any], planner_method: str) -> TaskIntentPrepareResponse:
        query = self._file_query(instruction, hints)
        steps = [
            TaskIntentPlanStep(id="step_1", type="file.search_connected_folders", query=query, purpose=f"Find files related to {query}", requires_user_selection=True),
            TaskIntentPlanStep(id="step_2", type="file.select_candidates", purpose="Let user choose files to summarize", requires_user_selection=True),
            TaskIntentPlanStep(id="step_3", type="document.summarize_selected_files", query=query, files_from_step="step_2", requires_confirmation=True),
            TaskIntentPlanStep(id="step_4", type="document.create_output_file", output_format="markdown", filename_hint=f"{self._slug(query)}-summary.md", requires_confirmation=True),
        ]
        return self._plan(intent="multi_step", primary_action="document.summaryFromSearch", risk_level="low", requires_user_selection=True, requires_confirmation=True, source_type="connected_files", needs_file_search=True, needs_user_file_selection=True, needs_output_file=True, entities=self._base_entities(hints, file_queries=[query], topic_queries=[query]), steps=steps, explanation=f"Search connected folders for files related to '{query}', then summarize selected files.", planner_method=planner_method)

    def _summary_then_gmail_plan(self, instruction: str, hints: dict[str, Any], recipients: list[str], wants_send: bool, planner_method: str) -> TaskIntentPrepareResponse:
        query = self._file_query(instruction, hints)
        gmail_type = "gmail.send_email_after_confirmation" if wants_send else "gmail.create_draft"
        steps = [
            TaskIntentPlanStep(id="step_1", type="file.search_connected_folders", query=query, requires_user_selection=True),
            TaskIntentPlanStep(id="step_2", type="file.select_candidates", requires_user_selection=True),
            TaskIntentPlanStep(id="step_3", type="document.summarize_selected_files", query=query, files_from_step="step_2", requires_confirmation=True),
            TaskIntentPlanStep(id="step_4", type="document.create_output_file", output_format="markdown", filename_hint=f"{self._slug(query)}-summary.md", requires_confirmation=True),
            TaskIntentPlanStep(id="step_5", type=gmail_type, to=recipients, subject_hint=f"Summary: {query}", body_hint="Brief professional email with the generated summary attached.", attachments_from_step="step_4", requires_confirmation=True),
        ]
        return self._plan(intent="multi_step", primary_action="gmail.sendGeneratedReport", risk_level="high" if wants_send else "medium", requires_user_selection=True, requires_confirmation=True, source_type="connected_files", needs_file_search=True, needs_user_file_selection=True, needs_output_file=True, entities=self._base_entities(hints, file_queries=[query], topic_queries=[query]), steps=steps, explanation=f"Search connected folders for files related to '{query}', create a summary, then prepare Gmail.", planner_method=planner_method)

    def _file_then_gmail_plan(self, instruction: str, hints: dict[str, Any], recipients: list[str], wants_send: bool, wants_draft: bool, planner_method: str) -> TaskIntentPrepareResponse:
        query = self._file_query(instruction, hints)
        email_step_type = "gmail.create_draft" if wants_draft or not wants_send else "gmail.send_email_after_confirmation"
        primary_action = "gmail.createDraft" if email_step_type == "gmail.create_draft" else "gmail.sendEmail"
        steps = [
            TaskIntentPlanStep(id="step_1", type="file.search_connected_folders", query=query, purpose=f"Find {query} attachment candidates", requires_user_selection=True),
            TaskIntentPlanStep(id="step_2", type="file.select_candidates", requires_user_selection=True),
            TaskIntentPlanStep(id="step_3", type=email_step_type, to=recipients, subject_hint="Resume for your review" if "resume" in query else "Requested file", body_hint="Brief professional email that mentions the selected attachment only after selection.", attachments_from_step="step_2", requires_confirmation=True),
        ]
        return self._plan(intent="multi_step", primary_action=primary_action, risk_level="high" if email_step_type == "gmail.send_email_after_confirmation" else "medium", requires_user_selection=True, requires_confirmation=True, source_type="connected_files", needs_file_search=True, needs_user_file_selection=True, needs_output_file=False, entities=self._base_entities(hints, file_queries=[query]), steps=steps, explanation=f"Search connected folders for {query}, then prepare Gmail with selected files.", planner_method=planner_method)

    def _log_plan(self, instruction: str, hints: dict[str, Any], planner_method: str) -> TaskIntentPrepareResponse:
        query = self._log_query(instruction, hints)
        steps = [
            TaskIntentPlanStep(id="step_1", type="log.search_connected_logs", query=query, extensions=LOG_EXTENSIONS, latest_preference=bool(hints.get("latest_preference")), exact_file_hint=str(hints.get("exact_file_hint") or "") or None, purpose="Find relevant log-like files in connected folders", requires_user_selection=True),
            TaskIntentPlanStep(id="step_2", type="file.select_candidates", requires_user_selection=True),
            TaskIntentPlanStep(id="step_3", type="log.analyze_selected_files", query=query, files_from_step="step_2", requires_confirmation=True),
            TaskIntentPlanStep(id="step_4", type="document.create_output_file", output_format="markdown", filename_hint=self._log_filename_hint(query), requires_confirmation=True),
        ]
        return self._plan(intent="multi_step", primary_action="log.analyzeFromSearch", risk_level="medium", requires_user_selection=True, requires_confirmation=True, source_type="connected_logs", needs_file_search=True, needs_user_file_selection=True, needs_output_file=True, entities=self._base_entities(hints, file_queries=[query], topic_queries=[query], extensions=LOG_EXTENSIONS), steps=steps, explanation=f"Search connected folders for log files related to '{query}', then create a redacted analysis report.", planner_method=planner_method)

    def _log_then_gmail_plan(self, instruction: str, hints: dict[str, Any], recipients: list[str], wants_send: bool, planner_method: str) -> TaskIntentPrepareResponse:
        query = self._log_query(instruction, hints)
        gmail_type = "gmail.send_email_after_confirmation" if wants_send else "gmail.create_draft"
        steps = [
            TaskIntentPlanStep(id="step_1", type="log.search_connected_logs", query=query, extensions=LOG_EXTENSIONS, latest_preference=bool(hints.get("latest_preference")), exact_file_hint=str(hints.get("exact_file_hint") or "") or None, purpose="Find relevant log-like files in connected folders", requires_user_selection=True),
            TaskIntentPlanStep(id="step_2", type="file.select_candidates", requires_user_selection=True),
            TaskIntentPlanStep(id="step_3", type="log.analyze_selected_files", query=query, files_from_step="step_2", requires_confirmation=True),
            TaskIntentPlanStep(id="step_4", type="document.create_output_file", output_format="markdown", filename_hint=self._log_filename_hint(query), requires_confirmation=True),
            TaskIntentPlanStep(id="step_5", type=gmail_type, to=recipients, subject_hint=f"Log analysis report: {query}", body_hint="Brief professional email with the generated log analysis report attached.", attachments_from_step="step_4", requires_confirmation=True),
        ]
        return self._plan(intent="multi_step", primary_action="gmail.sendGeneratedReport", risk_level="high" if wants_send else "medium", requires_user_selection=True, requires_confirmation=True, source_type="connected_logs", needs_file_search=True, needs_user_file_selection=True, needs_output_file=True, entities=self._base_entities(hints, file_queries=[query], topic_queries=[query], extensions=LOG_EXTENSIONS), steps=steps, explanation=f"Search connected folders for log files related to '{query}', create a report, then prepare Gmail.", planner_method=planner_method)

    def _organize_plan(self, instruction: str, hints: dict[str, Any], planner_method: str) -> TaskIntentPrepareResponse:
        return self._plan(intent="single_step", primary_action="file.organize", risk_level="medium", requires_user_selection=False, requires_confirmation=True, source_type="manual_files", needs_file_search=False, needs_user_file_selection=False, needs_output_file=False, entities=self._base_entities(hints), steps=[], explanation="Prepare a safe file organization preview after the user chooses a folder.", planner_method=planner_method)

    def _unsupported_plan(self, reason: str, hints: dict[str, Any], planner_method: str) -> TaskIntentPrepareResponse:
        return self._plan(intent="unsupported", primary_action="unsupported", risk_level="medium", requires_user_selection=False, requires_confirmation=True, source_type="none", needs_file_search=False, needs_user_file_selection=False, needs_output_file=False, entities=self._base_entities(hints), steps=[TaskIntentPlanStep(id="step_1", type="unsupported", purpose=reason)], explanation=reason, planner_method=planner_method, confidence=0.35)

    def _possible_intents(self, text: str, extensions: list[str], emails: list[str]) -> list[str]:
        intents: list[str] = []
        if self._is_log_analysis(text) or ".log" in extensions:
            intents.append("log.analyzeFromSearch")
        if self._is_summary_request(text):
            intents.append("document.summaryFromSearch")
        if emails or re.search(r"\b(gmail|email|mail)\b", text):
            intents.append("gmail.createDraft" if re.search(r"\b(draft|compose|write)\b", text) else "gmail.sendEmail")
        if self._is_organize_request(text):
            intents.append("file.organize")
        return intents or ["unsupported"]

    def _is_summary_request(self, text: str) -> bool:
        return bool(re.search(r"\b(summary|summarize|summarise|summarization|summarisation|report|recap)\b", text))

    def _is_organize_request(self, text: str) -> bool:
        return bool(re.search(r"\b(organize|organise|move|sort|clean|rename|copy)\b", text)) and bool(re.search(r"\b(folder|folders|files?|downloads|documents|desktop)\b", text))

    def _is_log_analysis(self, text: str) -> bool:
        has_log = bool(re.search(r"\b(log|logs|log files?|app\.log|server\.log|backend\.log|error\.log|debug\.log|traceback)\b", text) or re.search(r"\.(log|out|err)\b", text))
        has_analysis = bool(re.search(r"\b(error|errors|exception|failed|failure|traceback|stacktrace|timeout|root cause|causing|analyze|analyse|analysis|report|summary|summarize|summarization|database connection)\b", text))
        return has_log and has_analysis

    def _explicit_file_names(self, instruction: str) -> list[str]:
        return [match.strip() for match in re.findall(r"\b[\w .()_-]+\.[A-Za-z0-9]{2,5}\b", instruction) if match.strip()]

    def _extensions(self, instruction: str) -> list[str]:
        extensions = {self._normalize_extension(match) for match in re.findall(r"\.[A-Za-z0-9]{2,5}\b", instruction)}
        text = instruction.lower()
        if re.search(r"\blogs?\b", text):
            extensions.add(".log")
        if re.search(r"\bpdfs?\b", text):
            extensions.add(".pdf")
        if re.search(r"\bdocx?\b", text):
            extensions.add(".docx")
        if re.search(r"\bmarkdown|md\b", text):
            extensions.add(".md")
        if re.search(r"\btxt|text files?\b", text):
            extensions.add(".txt")
        return sorted(extensions)

    def _matched_words(self, text: str, candidates: list[str]) -> list[str]:
        return [candidate for candidate in candidates if re.search(rf"\b{re.escape(candidate)}\b", text)]

    def _topic_terms(self, instruction: str, action_words: list[str], connector_words: list[str]) -> list[str]:
        text = instruction.lower()
        stop = set(action_words + connector_words + ["from", "the", "a", "an", "of", "in", "my", "me", "please", "files", "file", "documents", "docs", "create", "make"])
        words = [word for word in re.findall(r"\b[a-z0-9][a-z0-9_-]*\b", text) if word not in stop and len(word) > 1]
        if "plan" in words and "2026" in words:
            return ["plan 2026"]
        return [" ".join(words[:5])] if words else []

    def _file_terms(self, instruction: str, explicit_file_names: list[str], topic_terms: list[str]) -> list[str]:
        if explicit_file_names:
            return explicit_file_names
        if re.search(r"\b(resume|cv|curriculum vitae)\b", instruction, flags=re.IGNORECASE):
            return ["resume cv curriculum vitae"]
        return topic_terms

    def _date_ranges(self, text: str) -> list[str]:
        ranges = []
        if re.search(r"\blast 7 days|past week\b", text):
            ranges.append("last_7_days")
        if re.search(r"\btoday\b", text):
            ranges.append("today")
        if re.search(r"\byesterday\b", text):
            ranges.append("yesterday")
        return ranges

    def _exact_file_hint(self, instruction: str) -> str | None:
        match = re.search(r"\b([A-Za-z0-9_. -]+\.(?:log|txt|out|err))\b", instruction)
        return match.group(1).strip() if match else None

    def _log_query(self, instruction: str, hints: dict[str, Any]) -> str:
        exact_file = str(hints.get("exact_file_hint") or "").strip()
        if exact_file:
            return exact_file
        topics = [str(item).strip() for item in hints.get("topic_terms") or [] if str(item).strip()]
        if topics:
            return topics[0]
        text = instruction.lower()
        text = re.sub(r"\b(find|search|analyze|analyse|analysis|check|logs?|logfiles?|log files?|files?|latest|recent|newest|make|create|summary|summarize|summarization|report|doc|document|about|and|the|a|an|what|is|causing|suggest|possible|solutions?)\b", " ", text)
        return re.sub(r"\s+", " ", text).strip() or "errors"

    def _log_filename_hint(self, query: str) -> str:
        return f"{self._slug(query) or 'log-error-analysis'}-report.md"

    def _file_query(self, instruction: str, hints: dict[str, Any]) -> str:
        exact_files = [str(item).strip() for item in hints.get("explicit_file_names") or [] if str(item).strip()]
        if exact_files:
            return " ".join(exact_files)
        file_terms = [str(item).strip() for item in hints.get("file_terms") or [] if str(item).strip()]
        if file_terms:
            return file_terms[0]
        if re.search(r"\b(resume|cv|curriculum vitae)\b", instruction, flags=re.IGNORECASE):
            return "resume cv curriculum vitae"
        text = re.sub(r"\[[^\]]+\]\(mailto:[^)]+\)", " ", instruction, flags=re.IGNORECASE)
        text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", " ", text, flags=re.IGNORECASE).lower()
        text = re.sub(r"\b(find|search|look up|lookup|files?|documents?|docs?|notes?|about|and|send|email|mail|gmail|summary|summarize|summarization|report|to|the|a|an|my|me|please|create|draft|from|of|make)\b", " ", text)
        return re.sub(r"\s+", " ", text).strip() or "selected files"

    def _normalize_extension(self, value: Any) -> str:
        extension = str(value).strip().lower()
        if not extension:
            return ""
        return extension if extension.startswith(".") else f".{extension}"

    def _safe_step_type(self, value: str) -> str:
        cleaned = value.strip()
        return cleaned if cleaned in ALLOWED_STEP_TYPES else "unsupported"

    def _slug(self, value: str) -> str:
        return re.sub(r"(^-|-$)", "", re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower()))).strip("-")


task_intent_planner_service = TaskIntentPlannerService()
