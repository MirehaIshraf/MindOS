import hashlib
import mimetypes
from pathlib import Path
from typing import Any


GENERATED_OUTPUT_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
GENERATED_OUTPUT_ALLOWED_EXTENSIONS = {".md", ".txt"}


class GeneratedOutputError(ValueError):
    pass


class GeneratedOutputService:
    def output_dir(self) -> Path:
        path = Path.home() / ".mindos" / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def attachment_id_for(self, file_name: str) -> str:
        safe_name = self._safe_file_name(file_name)
        digest = hashlib.sha256(f"mindos-output:{safe_name}".encode("utf-8")).hexdigest()[:16]
        return f"generated_{digest}"

    def metadata_for_path(self, path: Path, *, source_task_id: str | None = None, source_step_id: str | None = None) -> dict[str, str | int | bool | None]:
        resolved = self._resolve_inside_outputs(path.name)
        size = resolved.stat().st_size
        return {
            "id": self.attachment_id_for(resolved.name),
            "file_name": resolved.name,
            "path": str(resolved),
            "size_bytes": size,
            "mime_type": self.mime_type_for(resolved.name),
            "source_task_id": source_task_id,
            "source_step_id": source_step_id,
            "selected": True,
        }

    def read_gmail_attachments(self, references: list[Any] | None) -> list[dict[str, object]]:
        attachments: list[dict[str, object]] = []
        for reference in references or []:
            file_name = self._reference_value(reference, "file_name")
            attachment_id = self._reference_value(reference, "id")
            path = self._resolve_inside_outputs(file_name)
            expected_id = self.attachment_id_for(path.name)
            if attachment_id and attachment_id != expected_id:
                raise GeneratedOutputError("Generated attachment reference is invalid.")
            extension = path.suffix.lower()
            if extension not in GENERATED_OUTPUT_ALLOWED_EXTENSIONS:
                raise GeneratedOutputError(f"Generated output type is not attachable: {path.name}.")
            if not path.exists() or not path.is_file():
                raise GeneratedOutputError("Generated report file is missing. Recreate the report before sending.")
            size = path.stat().st_size
            if size > GENERATED_OUTPUT_MAX_ATTACHMENT_BYTES:
                raise GeneratedOutputError("Generated output is too large to attach. Keep attachments under 20 MB.")
            attachments.append(
                {
                    "filename": path.name,
                    "content_type": self.mime_type_for(path.name),
                    "content": path.read_bytes(),
                    "size": size,
                }
            )
        return attachments

    def mime_type_for(self, file_name: str) -> str:
        extension = Path(file_name).suffix.lower()
        if extension == ".md":
            return "text/markdown"
        if extension == ".txt":
            return "text/plain"
        return mimetypes.guess_type(file_name)[0] or "application/octet-stream"

    def _reference_value(self, reference: Any, key: str) -> str:
        if isinstance(reference, dict):
            value = reference.get(key)
        else:
            value = getattr(reference, key, None)
        return str(value or "").strip()

    def _resolve_inside_outputs(self, file_name: str) -> Path:
        safe_name = self._safe_file_name(file_name)
        output_root = self.output_dir().resolve()
        candidate = (output_root / safe_name).resolve()
        try:
            candidate.relative_to(output_root)
        except ValueError as error:
            raise GeneratedOutputError("Generated attachment path is outside MindOS outputs.") from error
        return candidate

    def _safe_file_name(self, file_name: str) -> str:
        cleaned = Path(str(file_name or "").strip()).name
        if not cleaned:
            raise GeneratedOutputError("Generated attachment filename is required.")
        if cleaned != str(file_name or "").strip():
            raise GeneratedOutputError("Generated attachment filename must not include a path.")
        if cleaned in {".", ".."} or any(part in cleaned for part in ["/", "\\", ":"]):
            raise GeneratedOutputError("Generated attachment filename is invalid.")
        return cleaned


generated_output_service = GeneratedOutputService()
