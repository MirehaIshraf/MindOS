import re
from collections import Counter
from pathlib import Path
from uuid import uuid4

from app.schemas.file_index import IndexedFileAttachmentReference
from app.schemas.file_tasks import (
    DocumentSummarySkippedFile,
    GeneratedSummarySaveRequest,
    GeneratedSummarySaveResponse,
    LogAnalysisPrepareRequest,
    LogAnalysisPrepareResponse,
    LogAnalysisSaveRequest,
    LogEvidenceFile,
)
from app.services.document_summary_naming_service import sanitize_filename_title
from app.services.document_summary_task_service import document_summary_task_service
from app.services.file_index_service import file_index_service
from app.services.model_router_service import model_router_service


LOG_EXTENSIONS = {".log", ".txt", ".out", ".err"}
ERROR_TERMS = ("error", "exception", "failed", "failure", "stacktrace", "traceback", "timeout", "refused", " 500 ", "panic")
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(access[_-]?token\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(refresh[_-]?token\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(token\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(secret\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


class LogAnalysisTaskService:
    def prepare(self, request: LogAnalysisPrepareRequest) -> LogAnalysisPrepareResponse:
        if not request.files:
            return LogAnalysisPrepareResponse(
                task_id=str(uuid4()),
                status="empty",
                report_title="No log files selected",
                report_markdown="Select at least one readable log file before creating a report.",
                output_filename_suggestion=self._filename_for(request.query, request.output_filename),
            )
        evidence, skipped, warnings = self._read_log_evidence(request.files)
        if not evidence:
            return LogAnalysisPrepareResponse(
                task_id=str(uuid4()),
                status="empty",
                report_title="No readable log evidence found",
                report_markdown="MindOS could not read useful evidence from the selected log files.",
                files_skipped=skipped,
                warnings=warnings or ["Selected files were not readable or exceeded safe limits."],
                output_filename_suggestion=self._filename_for(request.query, request.output_filename),
            )
        report = self._generate_report(request, evidence)
        return report.model_copy(update={"files_skipped": skipped, "warnings": [*warnings, *report.warnings]})

    def save(self, request: LogAnalysisSaveRequest) -> GeneratedSummarySaveResponse:
        return document_summary_task_service.save_output(
            GeneratedSummarySaveRequest(
                task_id=request.task_id,
                output_filename=request.output_filename,
                content=request.report_markdown,
            )
        )

    def _read_log_evidence(
        self,
        references: list,
        *,
        max_files: int = 10,
        max_chars_per_file: int = 50_000,
        max_total_chars: int = 150_000,
    ) -> tuple[list[LogEvidenceFile], list[DocumentSummarySkippedFile], list[str]]:
        evidence: list[LogEvidenceFile] = []
        skipped: list[DocumentSummarySkippedFile] = []
        warnings: list[str] = []
        total_chars = 0
        for reference in references[:max_files]:
            relative_path = reference.relative_path
            try:
                path = file_index_service.resolve_connected_file_path(
                    IndexedFileAttachmentReference(source_id=reference.source_id, relative_path=reference.relative_path)
                )
                extension = path.suffix.lower()
                if extension not in LOG_EXTENSIONS:
                    skipped.append(DocumentSummarySkippedFile(relative_path=relative_path, reason="Only .log and .txt files are supported for log analysis."))
                    continue
                if not path.exists() or not path.is_file():
                    skipped.append(DocumentSummarySkippedFile(relative_path=relative_path, reason="File is missing."))
                    continue
                remaining = max_total_chars - total_chars
                if remaining <= 0:
                    skipped.append(DocumentSummarySkippedFile(relative_path=relative_path, reason="Total log analysis limit reached."))
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                extracted = self._extract_evidence(relative_path, text, min(max_chars_per_file, remaining))
                if not any([extracted.error_lines, extracted.surrounding_context, extracted.last_lines]):
                    skipped.append(DocumentSummarySkippedFile(relative_path=relative_path, reason="No relevant log evidence found."))
                    continue
                total_chars += extracted.chars_used
                evidence.append(extracted)
            except Exception as error:
                skipped.append(DocumentSummarySkippedFile(relative_path=relative_path, reason=str(error)))
        if len(references) > max_files:
            warnings.append(f"Only the first {max_files} selected log files were analyzed.")
        if total_chars >= max_total_chars:
            warnings.append(f"Log analysis used the first {max_total_chars:,} extracted characters due to size limits.")
        return evidence, skipped, warnings

    def _extract_evidence(self, relative_path: str, text: str, max_chars: int) -> LogEvidenceFile:
        redacted = self._redact(text)
        lines = redacted.splitlines()
        error_indexes = [index for index, line in enumerate(lines) if self._looks_like_error(line)]
        error_lines = [self._trim(lines[index]) for index in error_indexes[:80]]
        context_lines: list[str] = []
        for index in error_indexes[:20]:
            start = max(0, index - 2)
            end = min(len(lines), index + 3)
            context_lines.append("\n".join(self._trim(line) for line in lines[start:end]))
        last_lines = [self._trim(line) for line in lines[-80:] if line.strip()][-40:]
        repeated_patterns = self._repeated_patterns(error_lines)
        chars_used = sum(len(item) for item in [*error_lines, *context_lines, *last_lines, *repeated_patterns])
        if chars_used > max_chars:
            budget = max_chars
            error_lines = self._fit_lines(error_lines, budget // 3)
            context_lines = self._fit_lines(context_lines, budget // 3)
            last_lines = self._fit_lines(last_lines, budget // 3)
            chars_used = sum(len(item) for item in [*error_lines, *context_lines, *last_lines, *repeated_patterns])
        return LogEvidenceFile(
            relative_path=relative_path,
            error_lines=error_lines,
            surrounding_context=context_lines,
            repeated_patterns=repeated_patterns,
            last_lines=last_lines,
            chars_used=chars_used,
        )

    def _generate_report(self, request: LogAnalysisPrepareRequest, evidence: list[LogEvidenceFile]) -> LogAnalysisPrepareResponse:
        prompt = self._build_prompt(request.query, evidence)
        result = model_router_service.generate(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are analyzing application log excerpts. Use only the provided log evidence. "
                        "Do not invent causes. Separate confirmed evidence from hypotheses. "
                        "Create a clear developer-friendly markdown report. Do not include secrets; obvious secrets are redacted."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            requested_model_id=request.model_id,
            options={"temperature": 0.2},
        )
        markdown = result.reply.strip() or self._deterministic_report(request.query, evidence)
        if not markdown.startswith("#"):
            markdown = f"# Log analysis report\n\n{markdown}"
        title = self._first_heading(markdown) or "Log analysis report"
        return LogAnalysisPrepareResponse(
            task_id=str(uuid4()),
            status="preview",
            report_title=title,
            report_markdown=markdown,
            files_used=[item.relative_path for item in evidence],
            output_filename_suggestion=self._filename_for(request.query, request.output_filename),
            evidence=evidence,
            model=result.model_used,
            provider=result.provider,
            model_display_name=result.model_display_name,
            planner_warning=result.warning,
        )

    def _build_prompt(self, query: str, evidence: list[LogEvidenceFile]) -> str:
        parts = [
            f"User query: {query}",
            "",
            "Create a markdown report with sections:",
            "1. Title",
            "2. Executive summary",
            "3. Files analyzed",
            "4. Key errors found",
            "5. Most likely root cause",
            "6. Evidence from logs",
            "7. Possible solutions",
            "8. Recommended next steps",
            "9. Uncertainties / missing information",
            "",
            "Log evidence:",
        ]
        for item in evidence:
            parts.extend(
                [
                    f"\n--- FILE: {item.relative_path} ---",
                    "Repeated patterns:",
                    "\n".join(item.repeated_patterns) or "None detected.",
                    "Key error lines:",
                    "\n".join(item.error_lines[:60]) or "No explicit error lines.",
                    "Surrounding context:",
                    "\n\n".join(item.surrounding_context[:12]) or "No surrounding context.",
                    "Last lines:",
                    "\n".join(item.last_lines[-30:]) or "No trailing lines.",
                ]
            )
        return "\n".join(parts)

    def _deterministic_report(self, query: str, evidence: list[LogEvidenceFile]) -> str:
        lines = [
            "# Log analysis report",
            "",
            "## Executive summary",
            f"MindOS analyzed {len(evidence)} selected log file(s) for `{query}` and found the evidence below.",
            "",
            "## Files analyzed",
        ]
        for item in evidence:
            lines.append(f"- `{item.relative_path}`")
        lines.extend(["", "## Key errors found"])
        for item in evidence:
            for line in item.error_lines[:10]:
                lines.append(f"- `{item.relative_path}`: {line}")
        lines.extend(
            [
                "",
                "## Most likely root cause",
                "The selected model was unavailable, so MindOS cannot make a confident causal judgment. Review the repeated patterns and error lines.",
                "",
                "## Evidence from logs",
            ]
        )
        for item in evidence:
            lines.append(f"### {item.relative_path}")
            lines.extend(f"- {pattern}" for pattern in item.repeated_patterns[:8])
        lines.extend(["", "## Possible solutions", "- Review the error lines above and inspect the related service/configuration.", "", "## Recommended next steps", "- Re-run the failing workflow with debug logging if the evidence is incomplete.", "", "## Uncertainties / missing information", "- This fallback report is based only on selected log excerpts."])
        return "\n".join(lines)

    def _redact(self, value: str) -> str:
        redacted = value
        for pattern in SECRET_PATTERNS:
            if pattern.pattern.startswith("-----BEGIN"):
                redacted = pattern.sub("[REDACTED]", redacted)
            else:
                redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        return redacted

    def _looks_like_error(self, line: str) -> bool:
        lowered = f" {line.lower()} "
        return any(term in lowered for term in ERROR_TERMS)

    def _trim(self, value: str, limit: int = 500) -> str:
        return re.sub(r"\s+", " ", value).strip()[:limit]

    def _repeated_patterns(self, error_lines: list[str]) -> list[str]:
        normalized = [re.sub(r"\d+", "#", line.lower())[:160] for line in error_lines if line.strip()]
        counts = Counter(normalized)
        return [f"{count}x {pattern}" for pattern, count in counts.most_common(12) if count > 1]

    def _fit_lines(self, lines: list[str], budget: int) -> list[str]:
        output: list[str] = []
        used = 0
        for line in lines:
            if used + len(line) > budget:
                break
            output.append(line)
            used += len(line)
        return output

    def _first_heading(self, markdown: str) -> str | None:
        for line in markdown.splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return None

    def _filename_for(self, query: str, requested_filename: str | None) -> str:
        if requested_filename and requested_filename.strip():
            return sanitize_filename_title(requested_filename.strip(), ".md", append_summary=False)
        topic = re.sub(r"\b(latest|logs?|files?|find|search|analyze|check|errors?|make|report)\b", " ", query.lower())
        topic = re.sub(r"\s+", " ", topic).strip() or "log-error-analysis"
        return sanitize_filename_title(f"{topic}-report.md", ".md", append_summary=False)


log_analysis_task_service = LogAnalysisTaskService()
