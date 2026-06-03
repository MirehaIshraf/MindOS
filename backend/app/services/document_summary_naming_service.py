import json
import re
from collections import Counter
from dataclasses import dataclass

from app.schemas.file_tasks import DocumentSummaryInputFile
from app.services.model_router_service import model_router_service


GENERIC_TERMS = {
    "summary",
    "final",
    "copy",
    "draft",
    "document",
    "documents",
    "notes",
    "note",
    "report",
    "file",
    "files",
    "new",
    "version",
    "updated",
    "read",
    "these",
    "all",
    "selected",
    "folder",
}


@dataclass
class DocumentSummaryNaming:
    summary_title: str
    output_filename_suggestion: str
    topic: str
    confidence: str
    method: str


class DocumentSummaryNamingService:
    def generate(
        self,
        *,
        instruction: str,
        folder_name: str,
        files: list[DocumentSummaryInputFile],
        summary_markdown: str,
        output_format: str,
        use_llm: bool,
    ) -> DocumentSummaryNaming:
        deterministic = self.generate_deterministic(
            instruction=instruction,
            folder_name=folder_name,
            files=files,
            summary_markdown=summary_markdown,
            output_format=output_format,
        )
        if not use_llm:
            return deterministic

        llm_naming = self._generate_with_llm(
            instruction=instruction,
            files=files,
            summary_markdown=summary_markdown,
            output_format=output_format,
        )
        return llm_naming or deterministic

    def generate_deterministic(
        self,
        *,
        instruction: str,
        folder_name: str,
        files: list[DocumentSummaryInputFile],
        summary_markdown: str,
        output_format: str,
    ) -> DocumentSummaryNaming:
        topic, confidence = self._infer_topic(instruction, folder_name, files, summary_markdown)
        extension = ".txt" if output_format == "text" else ".md"
        filename = sanitize_filename_title(f"{topic} summary" if topic else "mindos summary", extension)
        return DocumentSummaryNaming(
            summary_title=self._title_for(topic),
            output_filename_suggestion=filename,
            topic=topic,
            confidence=confidence,
            method="deterministic" if topic else "fallback",
        )

    def _generate_with_llm(
        self,
        *,
        instruction: str,
        files: list[DocumentSummaryInputFile],
        summary_markdown: str,
        output_format: str,
    ) -> DocumentSummaryNaming | None:
        extension = ".txt" if output_format == "text" else ".md"
        prompt = "\n".join(
            [
                "Generate a short task title and safe filename for this document summary.",
                "Return JSON only with keys: summary_title, topic, output_filename_suggestion.",
                "Rules:",
                "- filename must be lowercase kebab-case.",
                f"- filename must end with {extension}.",
                "- filename max 60 characters before extension.",
                "- do not invent a topic not supported by the content.",
                f"User instruction: {instruction}",
                f"Files: {', '.join(file.relative_path for file in files[:20])}",
                f"Summary excerpt: {summary_markdown[:1000]}",
            ]
        )
        try:
            result = model_router_service.generate(
                messages=[
                    {"role": "system", "content": "You create concise document summary names. Return strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.1},
            )
            data = json.loads(self._strip_code_fences(result.reply.strip()))
            topic = str(data.get("topic") or "").strip()
            title = str(data.get("summary_title") or "").strip()
            filename = str(data.get("output_filename_suggestion") or "").strip()
            if not topic and not title and not filename:
                return None
            topic = self._clean_topic(topic or title)
            return DocumentSummaryNaming(
                summary_title=title if title else self._title_for(topic),
                output_filename_suggestion=sanitize_filename_title(filename or f"{topic} summary", extension),
                topic=topic,
                confidence="high" if topic else "low",
                method="llm",
            )
        except Exception:
            return None

    def _infer_topic(
        self,
        instruction: str,
        folder_name: str,
        files: list[DocumentSummaryInputFile],
        summary_markdown: str,
    ) -> tuple[str, str]:
        heading_topic = self._first_heading_topic(summary_markdown)
        if heading_topic:
            return heading_topic, "high"

        document_heading = self._first_document_heading(files)
        if document_heading:
            return document_heading, "high"

        file_topic = self._topic_from_filenames(files)
        folder_topic = self._clean_topic(folder_name)
        instruction_topic = self._topic_from_instruction(instruction)

        if file_topic and folder_topic and self._shares_meaningful_term(file_topic, folder_topic):
            combined = self._merge_short_topics(folder_topic, file_topic)
            return combined, "high"
        if file_topic:
            return file_topic, "medium"
        if instruction_topic:
            return instruction_topic, "medium"
        if folder_topic:
            return folder_topic, "medium"
        return "", "low"

    def _first_heading_topic(self, summary_markdown: str) -> str:
        for raw_line in summary_markdown.splitlines()[:20]:
            line = raw_line.strip().lstrip("#").strip()
            topic = self._clean_topic(line)
            if topic and not topic.lower().startswith(("summary of", "overview", "key points", "file by file")):
                return topic
        return ""

    def _first_document_heading(self, files: list[DocumentSummaryInputFile]) -> str:
        for file in files[:8]:
            for raw_line in file.text.splitlines()[:20]:
                line = raw_line.strip().lstrip("#").strip()
                if 6 <= len(line) <= 80:
                    topic = self._clean_topic(line)
                    if topic:
                        return topic
        return ""

    def _topic_from_filenames(self, files: list[DocumentSummaryInputFile]) -> str:
        token_counter: Counter[str] = Counter()
        ordered_tokens: list[str] = []
        for file in files:
            stem = re.sub(r"\.[^.]+$", "", file.relative_path.split("/")[-1])
            for token in self._tokens(stem):
                token_counter[token.lower()] += 1
                if token not in ordered_tokens:
                    ordered_tokens.append(token)
        repeated = [token for token in ordered_tokens if token_counter[token.lower()] > 1]
        chosen = repeated or ordered_tokens
        return self._clean_topic(" ".join(chosen[:6]))

    def _topic_from_instruction(self, instruction: str) -> str:
        cleaned = re.sub(r"\b(summarize|summary|create|make|read|documents?|files?|folder|all|these|this)\b", " ", instruction, flags=re.I)
        return self._clean_topic(cleaned)

    def _clean_topic(self, value: str) -> str:
        words = self._tokens(value)
        filtered = [word for word in words if word.lower() not in GENERIC_TERMS]
        return " ".join(filtered[:6]).strip()

    def _tokens(self, value: str) -> list[str]:
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
        spaced = re.sub(r"[_\-./\\]+", " ", spaced)
        return [token for token in re.findall(r"[A-Za-z0-9]+", spaced) if len(token) > 1]

    def _shares_meaningful_term(self, left: str, right: str) -> bool:
        left_terms = {term.lower() for term in self._tokens(left) if term.lower() not in GENERIC_TERMS}
        right_terms = {term.lower() for term in self._tokens(right) if term.lower() not in GENERIC_TERMS}
        return bool(left_terms & right_terms)

    def _merge_short_topics(self, left: str, right: str) -> str:
        merged: list[str] = []
        for token in self._tokens(f"{left} {right}"):
            if token.lower() not in {item.lower() for item in merged}:
                merged.append(token)
        return " ".join(merged[:6])

    def _title_for(self, topic: str) -> str:
        if not topic:
            return "Created document summary"
        lower = topic.lower()
        if "project" in lower:
            return f"Created {topic} overview"
        if "model" in lower:
            return f"Summarized {topic} notes"
        return f"Summarized {topic} documents"

    def _strip_code_fences(self, value: str) -> str:
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value.strip(), flags=re.I).strip()
            value = re.sub(r"```$", "", value).strip()
        return value


def sanitize_filename_title(value: str, extension: str, append_summary: bool = True) -> str:
    safe_extension = ".txt" if extension == ".txt" else ".md"
    stem = re.sub(r"\.(md|txt)$", "", value.strip(), flags=re.I)
    stem = re.sub(r"[\\/:*?\"<>|#%&{}$!'@+`=]+", " ", stem)
    stem = re.sub(r"[_\s]+", "-", stem.lower())
    stem = re.sub(r"[^a-z0-9-]+", "", stem)
    stem = re.sub(r"-+", "-", stem).strip("-")
    if append_summary and stem and not stem.endswith("summary") and not stem.endswith("overview"):
        stem = f"{stem}-summary"
    stem = stem[:60].strip("-")
    if not stem:
        stem = "mindos-summary"
    return f"{stem}{safe_extension}"


document_summary_naming_service = DocumentSummaryNamingService()
