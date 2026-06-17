from uuid import uuid4
from pathlib import Path

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.repositories.base import EventRepository
from app.schemas.file_tasks import (
    DocumentSummaryCompleteRequest,
    DocumentSummaryCompleteResponse,
    DocumentSummaryInputFile,
    DocumentSummaryPrepareRequest,
    DocumentSummaryPrepareResponse,
    GeneratedSummarySaveRequest,
    GeneratedSummarySaveResponse,
    GeneratedSummaryOutputFile,
    IndexedDocumentSummaryPrepareRequest,
)
from app.schemas.file_index import IndexedFileAttachmentReference
from app.services.file_index_service import file_index_service
from app.services.generated_output_service import generated_output_service
from app.services.model_router_service import model_router_service
from app.services.relationship_service import relationship_service
from app.services.task_memory_policy_service import should_create_memory_for_task
from app.services.document_summary_naming_service import document_summary_naming_service, sanitize_filename_title


UNSAFE_DOCUMENT_SUMMARY_TERMS = {"delete", "rewrite all", "edit these", "upload", "email", "overwrite", "execute", "run "}


class DocumentSummaryTaskService:
    def __init__(self, events: EventRepository | None = None) -> None:
        self._events = events or get_event_repository()

    def prepare_summary(self, request: DocumentSummaryPrepareRequest) -> DocumentSummaryPrepareResponse:
        if self._is_unsafe(request.instruction):
            return DocumentSummaryPrepareResponse(
                task_id=str(uuid4()),
                status="unsupported",
                summary_title="Document summary not supported for this request",
                summary_markdown="MindOS cannot safely perform this document task yet.",
                files_skipped=request.files_skipped,
                warnings=["This request appears to ask for editing, deleting, uploading, emailing, overwriting, or executing files."],
                output_filename_suggestion=self._filename_for(request.output_format, request.output_filename),
                output_format=request.output_format,
                summary_style=request.summary_style,
            )

        if not request.files:
            return DocumentSummaryPrepareResponse(
                task_id=str(uuid4()),
                status="empty",
                summary_title="No readable documents found",
                summary_markdown="I couldn't find readable documents in this folder.",
                files_skipped=request.files_skipped,
                warnings=["MindOS can currently summarize txt, md, log, json, csv, selectable-text PDF, and DOCX files in browser-selected folders."],
                output_filename_suggestion=self._filename_for(request.output_format, request.output_filename),
                output_format=request.output_format,
                summary_style=request.summary_style,
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You summarize local user-selected documents. Do not invent facts. "
                    "Use only the provided document text. If information is missing, say it is missing. "
                    "Mention when content was truncated. Follow the requested summary style and output format."
                ),
            },
            {"role": "user", "content": self._build_prompt(request)},
        ]
        result = model_router_service.generate(
            messages=messages,
            requested_model_id=request.model_id,
            options={"temperature": 0.2},
        )
        summary = result.reply.strip() or self._deterministic_summary(request.files)
        if request.output_format == "markdown" and not summary.startswith("#"):
            summary = f"# Summary of selected documents\n\n{summary}"
        naming = document_summary_naming_service.generate(
            instruction=request.instruction,
            folder_name=request.folder_name,
            files=request.files,
            summary_markdown=summary,
            output_format=request.output_format,
            use_llm=result.provider != "fake",
        )
        requested_filename = request.output_filename.strip() if request.output_filename else ""

        return DocumentSummaryPrepareResponse(
            task_id=str(uuid4()),
            status="preview",
            summary_title=naming.summary_title,
            summary_markdown=summary,
            files_used=[file.relative_path for file in request.files],
            files_skipped=request.files_skipped,
            warnings=[],
            output_filename_suggestion=self._filename_for(
                request.output_format,
                requested_filename if requested_filename and requested_filename.lower() not in {"mindos-summary.md", "mindos-summary.txt"} else naming.output_filename_suggestion,
            ),
            model=result.model_used,
            provider=result.provider,
            model_display_name=result.model_display_name,
            planner_warning=result.warning,
            output_format=request.output_format,
            summary_style=request.summary_style,
            topic=naming.topic,
            naming_confidence=naming.confidence,
            naming_method=naming.method,
        )

    def prepare_summary_from_indexed_files(self, request: IndexedDocumentSummaryPrepareRequest) -> DocumentSummaryPrepareResponse:
        if not request.files:
            return DocumentSummaryPrepareResponse(
                task_id=str(uuid4()),
                status="empty",
                summary_title="No files selected",
                summary_markdown="Select at least one readable file before creating a summary.",
                output_filename_suggestion=self._filename_for(request.output_format, request.output_filename or f"{request.query}-summary"),
                output_format=request.output_format,
                summary_style=request.style,
            )
        references = [IndexedFileAttachmentReference(source_id=file.source_id, relative_path=file.relative_path) for file in request.files]
        files, skipped, warnings, folder_name = file_index_service.read_indexed_documents(references)
        style = "report" if request.style == "report" else request.style
        if not files:
            return DocumentSummaryPrepareResponse(
                task_id=str(uuid4()),
                status="empty",
                summary_title="No readable selected files",
                summary_markdown="MindOS could not read the selected files for a summary.",
                files_skipped=skipped,
                warnings=warnings or ["Selected files were not readable or exceeded safe limits."],
                output_filename_suggestion=self._filename_for(request.output_format, request.output_filename or f"{request.query}-summary"),
                output_format=request.output_format,
                summary_style=style,
            )
        instruction = (
            f"Create a report about {request.query} from selected connected-folder files."
            if request.style == "report"
            else f"Create a summary about {request.query} from selected connected-folder files."
        )
        summary_request = DocumentSummaryPrepareRequest(
            instruction=instruction,
            folder_name=folder_name,
            files=files,
            files_skipped=skipped,
            output_format=request.output_format,
            output_filename=request.output_filename or f"{request.query}-{'report' if request.style == 'report' else 'summary'}",
            summary_style=style,
            model_id=request.model_id,
        )
        response = self.prepare_summary(summary_request)
        return response.model_copy(update={"warnings": [*warnings, *response.warnings], "files_skipped": skipped})

    def save_output(self, request: GeneratedSummarySaveRequest) -> GeneratedSummarySaveResponse:
        output_dir = generated_output_service.output_dir()
        extension = ".txt" if request.output_filename.lower().endswith(".txt") else ".md"
        safe_name = sanitize_filename_title(request.output_filename, extension, append_summary=False)
        path = self._unique_output_path(output_dir, safe_name)
        path.write_text(request.content, encoding="utf-8")
        metadata = generated_output_service.metadata_for_path(path, source_task_id=request.task_id, source_step_id="document.create_output_file")
        return GeneratedSummarySaveResponse(
            output_file=GeneratedSummaryOutputFile(**metadata)
        )

    def complete_summary(self, request: DocumentSummaryCompleteRequest) -> DocumentSummaryCompleteResponse:
        task_type = "document_summary"
        if not should_create_memory_for_task(task_type):
            return DocumentSummaryCompleteResponse(status="completed_with_warning", warning="Task memory policy skipped memory creation.")

        content = (
            f"Created {request.output_file_name} from {request.files_used_count} selected files"
            f" in {request.folder_name}."
        )
        title = request.summary_title.strip() if request.summary_title and request.summary_title.strip() else "Created document summary"
        metadata = {
            "task_id": request.task_id,
            "task_type": task_type,
            "topic": request.topic,
            "output_file_name": request.output_file_name,
            "folder_name": request.folder_name,
            "files_used_count": request.files_used_count,
            "files_skipped_count": request.files_skipped_count,
            "summary_style": request.summary_style,
            "output_format": request.output_format,
            "file_types_used": sorted(set(request.file_types_used)),
            "naming_confidence": request.naming_confidence,
            "memory_category": "task",
            "hidden_from_default": False,
        }
        try:
            event = self._events.create_event(
                {
                    "source": EventSource.mindos,
                    "type": "document_summary_created",
                    "title": title,
                    "content": content,
                    "metadata": metadata,
                    "embedding_status": EmbeddingStatus.not_required,
                }
            )
            relationship_service.detect_relationships_for_event(event)
            return DocumentSummaryCompleteResponse(status="recorded", memory_event_id=event.id)
        except Exception as error:
            return DocumentSummaryCompleteResponse(
                status="completed_with_warning",
                warning=f"Summary was saved, but MindOS could not record the memory event: {error}",
            )

    def _build_prompt(self, request: DocumentSummaryPrepareRequest) -> str:
        parts = [
            f"User instruction: {request.instruction}",
            f"Folder: {request.folder_name}",
            f"Output format: {request.output_format}",
            f"Summary style: {request.summary_style}",
            self._style_instruction(request.summary_style),
            "Summarize only these extracted document texts:",
        ]
        for file in request.files:
            parts.append(f"\n--- FILE: {file.relative_path} ({file.extension}) ---\n{file.text}")
        return "\n".join(parts)

    def _deterministic_summary(self, files: list[DocumentSummaryInputFile]) -> str:
        lines = [
            "# Summary of selected documents",
            "",
            "## Overview",
            f"MindOS read {len(files)} supported documents and prepared a basic summary from their extracted text.",
            "",
            "## Key points",
        ]
        for file in files[:8]:
            excerpt = " ".join(file.text.split())[:280]
            lines.append(f"- `{file.relative_path}`: {excerpt}{'...' if len(file.text) > 280 else ''}")
        lines.extend(["", "## File-by-file notes"])
        for file in files[:8]:
            excerpt = " ".join(file.text.split())[:600]
            lines.extend([f"### {file.relative_path}", excerpt or "No readable text extracted.", ""])
        lines.extend(["## Open questions / missing information", "- This deterministic fallback summary may be incomplete."])
        return "\n".join(lines)

    def _is_unsafe(self, instruction: str) -> bool:
        text = instruction.lower()
        return any(term in text for term in UNSAFE_DOCUMENT_SUMMARY_TERMS)

    def _style_instruction(self, summary_style: str) -> str:
        if summary_style == "brief":
            return "Style instructions: write a concise overview and key points only. Avoid a long file-by-file section unless necessary."
        if summary_style == "file_by_file":
            return "Style instructions: group the summary by each file first, then add final combined observations."
        if summary_style == "report":
            return "Style instructions: write a report with title, executive summary, key findings, details by file, open questions or missing evidence, and suggested next steps if relevant."
        return "Style instructions: include overview, key points, important details, file-by-file notes, and missing or unclear information."

    def _filename_for(self, output_format: str, requested_filename: str | None = None) -> str:
        extension = ".txt" if output_format == "text" else ".md"
        if requested_filename and requested_filename.strip():
            return sanitize_filename_title(requested_filename.strip(), extension, append_summary=False)
        return "mindos-summary.txt" if output_format == "text" else "mindos-summary.md"

    def _unique_output_path(self, output_dir: Path, file_name: str) -> Path:
        candidate = output_dir / file_name
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        for index in range(1, 1000):
            next_candidate = output_dir / f"{stem}-{index}{suffix}"
            if not next_candidate.exists():
                return next_candidate
        raise ValueError("Could not create a unique output filename.")


document_summary_task_service = DocumentSummaryTaskService()
