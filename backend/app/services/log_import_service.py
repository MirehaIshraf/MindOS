from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus
from app.repositories.base import EventRepository
from app.schemas.connectors import (
    LogImportRequest,
    LogImportResult,
    LogLinePreview,
    LogPreviewRequest,
    LogPreviewResult,
)
from app.services.relationship_service import relationship_service

ALLOWED_LOG_EXTENSIONS = {".log", ".txt", ".out", ".err"}
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024
ERROR_LEVELS = {"ERROR", "ERR", "FATAL", "CRITICAL", "EXCEPTION", "TRACEBACK"}
WARNING_LEVELS = {"WARN", "WARNING"}
SIGNIFICANT_INFO_MARKERS = {"fail", "failed", "error", "exception", "timeout", "retry", "denied", "login", "auth"}
TIMESTAMP_PATTERNS = [
    re.compile(r"\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\]?"),
    re.compile(r"\[?(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})\]?"),
]


class ParsedLogLine:
    def __init__(self, line_number: int, raw: str, level: str, message: str, detected_timestamp: str | None) -> None:
        self.line_number = line_number
        self.raw = raw
        self.level = level
        self.message = message
        self.detected_timestamp = detected_timestamp


class LogImportService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()

    def preview_log(self, request: LogPreviewRequest) -> LogPreviewResult:
        path = self._validate_file(request.file_path)
        parsed, skipped, total = self._read_matching_lines(path, request.max_lines, request.only_errors)
        parsed.sort(key=lambda item: (self._level_priority(item.level), item.line_number))
        preview = [
            LogLinePreview(
                line_number=line.line_number,
                level=line.level,
                message=line.message,
                timestamp=line.detected_timestamp,
                raw=line.raw,
            )
            for line in parsed[:100]
        ]
        return LogPreviewResult(
            file_path=str(path.resolve()),
            total_lines_scanned=total,
            matched_lines=len(parsed),
            preview=preview,
            skipped=skipped,
            message=f"Found {len(parsed)} relevant log lines.",
        )

    def import_log(self, request: LogImportRequest) -> LogImportResult:
        path = self._validate_file(request.file_path)
        parsed, skipped, _ = self._read_matching_lines(path, request.max_lines, request.only_errors)
        existing = self._existing_hashes()
        events_created: list[str] = []
        failed_count = 0
        groups_created = 0

        if request.group_similar:
            groups = self._group_lines(parsed)
            groups_created = len(groups)
            for group in groups:
                try:
                    event_id = self._create_group_event(path, group, existing)
                    if event_id:
                        events_created.append(event_id)
                    else:
                        skipped.append({"path": str(path), "reason": "already_imported"})
                except Exception:
                    failed_count += 1
        else:
            for line in parsed:
                try:
                    event_id = self._create_line_event(path, line, existing)
                    if event_id:
                        events_created.append(event_id)
                    else:
                        skipped.append({"path": str(path), "line_number": line.line_number, "reason": "already_imported"})
                except Exception:
                    failed_count += 1

        return LogImportResult(
            imported_count=len(events_created),
            skipped_count=len(skipped),
            failed_count=failed_count,
            events_created=events_created,
            groups_created=groups_created if request.group_similar else 0,
            message=f"Imported {len(events_created)} log memory events.",
        )

    def _validate_file(self, file_path: str) -> Path:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise ValueError("Log file path does not exist.")
        if not path.is_file():
            raise ValueError("Log path must be a file.")
        if path.suffix.lower() not in ALLOWED_LOG_EXTENSIONS:
            raise ValueError("Unsupported log file type.")
        if path.stat().st_size > MAX_LOG_SIZE_BYTES:
            raise ValueError("Log file is larger than 10MB.")
        with path.open("rb") as handle:
            if b"\x00" in handle.read(4096):
                raise ValueError("Binary log files are not supported.")
        return path

    def _read_matching_lines(self, path: Path, max_lines: int, only_errors: bool) -> tuple[list[ParsedLogLine], list[dict], int]:
        parsed: list[ParsedLogLine] = []
        skipped: list[dict] = []
        total = 0
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for total, raw_line in enumerate(handle, start=1):
                    if total > max_lines:
                        break
                    raw = raw_line.rstrip("\n")
                    line = self._parse_line(total, raw)
                    if self._should_import(line, only_errors):
                        parsed.append(line)
        except OSError as error:
            skipped.append({"path": str(path), "reason": str(error)})
        return parsed, skipped, min(total, max_lines)

    def _parse_line(self, line_number: int, raw: str) -> ParsedLogLine:
        upper = raw.upper()
        if "TRACEBACK" in upper:
            level = "TRACEBACK"
        elif any(marker in upper for marker in ["CRITICAL", "FATAL", "EXCEPTION", "ERROR", "ERR"]):
            level = "ERROR"
        elif any(marker in upper for marker in ["WARNING", "WARN"]):
            level = "WARNING"
        elif "INFO" in upper:
            level = "INFO"
        elif "DEBUG" in upper:
            level = "DEBUG"
        else:
            level = "unknown"
        timestamp = self._detect_timestamp(raw)
        message = self._strip_timestamp(raw).strip() or raw
        return ParsedLogLine(line_number=line_number, raw=raw, level=level, message=message[:500], detected_timestamp=timestamp)

    def _detect_timestamp(self, raw: str) -> str | None:
        for pattern in TIMESTAMP_PATTERNS:
            match = pattern.search(raw)
            if match:
                return match.group(1).replace("T", " ")
        return None

    def _strip_timestamp(self, raw: str) -> str:
        value = raw
        for pattern in TIMESTAMP_PATTERNS:
            value = pattern.sub("", value, count=1)
        return value.strip(" []-")

    def _should_import(self, line: ParsedLogLine, only_errors: bool) -> bool:
        if line.level in ERROR_LEVELS or line.level == "ERROR":
            return True
        if only_errors:
            return False
        if line.level == "WARNING":
            return True
        if line.level == "INFO":
            return any(marker in line.message.lower() for marker in SIGNIFICANT_INFO_MARKERS)
        return False

    def _group_lines(self, lines: list[ParsedLogLine]) -> list[list[ParsedLogLine]]:
        grouped: dict[str, list[ParsedLogLine]] = defaultdict(list)
        for line in lines:
            key = f"{line.level}:{self._normalize_message(line.message)}"
            grouped[key].append(line)
        return list(grouped.values())

    def _normalize_message(self, message: str) -> str:
        value = message.lower()
        value = re.sub(r"\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}", "", value)
        value = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "", value)
        value = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "", value)
        value = re.sub(r"\d+", "", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    def _create_group_event(self, path: Path, group: list[ParsedLogLine], existing: set[str]) -> str | None:
        first = group[0]
        last = group[-1]
        normalized = self._normalize_message(first.message)
        group_hash = hashlib.sha256(f"{path.resolve()}:{first.level}:{normalized}:{len(group)}:{first.line_number}:{last.line_number}".encode()).hexdigest()
        if group_hash in existing:
            return None
        samples = "\n".join(line.raw for line in group[:5])
        content = (
            f"Summary: {first.message}\n"
            f"Occurrence count: {len(group)}\n"
            f"First line: {first.line_number}\n"
            f"Last line: {last.line_number}\n\n"
            f"Sample lines:\n{samples}"
        )
        event = self._event_repository.create_event(
            {
                "source": "logs",
                "type": self._event_type(first.level),
                "title": f"{first.level} repeated {len(group)} times: {self._short(first.message)}",
                "content": content,
                "metadata": {
                    "file_path": str(path.resolve()),
                    "file_name": path.name,
                    "level": first.level,
                    "occurrence_count": len(group),
                    "first_line_number": first.line_number,
                    "last_line_number": last.line_number,
                    "normalized_message_hash": group_hash,
                    "grouped": True,
                    "import_method": "manual_log_import",
                },
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        existing.add(group_hash)
        relationship_service.detect_relationships_for_event(event)
        return event.id

    def _create_line_event(self, path: Path, line: ParsedLogLine, existing: set[str]) -> str | None:
        content_hash = hashlib.sha256(f"{path.resolve()}:{line.line_number}:{line.raw}".encode()).hexdigest()
        if content_hash in existing:
            return None
        event = self._event_repository.create_event(
            {
                "source": "logs",
                "type": self._event_type(line.level),
                "title": f"{line.level}: {self._short(line.message)}",
                "content": line.raw,
                "metadata": {
                    "file_path": str(path.resolve()),
                    "file_name": path.name,
                    "line_number": line.line_number,
                    "level": line.level,
                    "detected_timestamp": line.detected_timestamp,
                    "content_hash": content_hash,
                    "grouped": False,
                    "import_method": "manual_log_import",
                },
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        existing.add(content_hash)
        relationship_service.detect_relationships_for_event(event)
        return event.id

    def _existing_hashes(self) -> set[str]:
        hashes: set[str] = set()
        for event in self._event_repository.list_all_events(include_hidden=True):
            if event.source.value != "logs":
                continue
            for key in ["content_hash", "normalized_message_hash"]:
                value = event.metadata.get(key)
                if isinstance(value, str):
                    hashes.add(value)
        return hashes

    def _event_type(self, level: str) -> str:
        if level in ERROR_LEVELS or level == "ERROR":
            return "log_error"
        if level == "WARNING":
            return "log_warning"
        return "log_info"

    def _level_priority(self, level: str) -> int:
        if self._event_type(level) == "log_error":
            return 0
        if self._event_type(level) == "log_warning":
            return 1
        return 2

    def _short(self, value: str) -> str:
        return value[:90]
