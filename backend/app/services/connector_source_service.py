from datetime import datetime, timezone
from typing import Any

from app.core.dependencies import get_connector_source_repository, get_event_repository, get_relationship_repository
from app.repositories.base import ConnectorSourceRepository, EventRepository, RelationshipRepository
from app.schemas.connectors import (
    ConnectorSourceCreateRequest,
    ConnectorSourceResponse,
    ConnectorSourcesResponse,
    ConnectorSourceUpdateRequest,
    FileImportRequest,
    GitImportRequest,
    ImportRunResponse,
    ImportRunsResponse,
    LogImportRequest,
)
from app.services.file_import_service import FileImportService
from app.services.git_import_service import GitImportService
from app.services.log_import_service import LogImportService


class ConnectorSourceService:
    def __init__(
        self,
        source_repository: ConnectorSourceRepository | None = None,
        event_repository: EventRepository | None = None,
        relationship_repository: RelationshipRepository | None = None,
    ) -> None:
        self._source_repository = source_repository or get_connector_source_repository()
        self._event_repository = event_repository or get_event_repository()
        self._relationship_repository = relationship_repository or get_relationship_repository()
        self._file_import_service = FileImportService(self._event_repository)
        self._log_import_service = LogImportService(self._event_repository)
        self._git_import_service = GitImportService(self._event_repository)

    def create_source(self, request: ConnectorSourceCreateRequest) -> ConnectorSourceResponse:
        source = self._source_repository.create_source(
            {
                "connector_type": request.connector_type,
                "name": request.name.strip(),
                "path": request.path.strip(),
                "config": request.config,
                "enabled": request.enabled,
            }
        )
        return ConnectorSourceResponse(**source.model_dump())

    def update_source(self, source_id: str, request: ConnectorSourceUpdateRequest) -> ConnectorSourceResponse:
        source = self._source_repository.update_source(source_id, request.model_dump(exclude_unset=True))
        return ConnectorSourceResponse(**source.model_dump())

    def delete_source(self, source_id: str) -> bool:
        return self._source_repository.delete_source(source_id)

    def list_sources(self, connector_type: str | None = None) -> ConnectorSourcesResponse:
        sources = self._source_repository.list_sources(connector_type=connector_type)
        return ConnectorSourcesResponse(
            sources=[ConnectorSourceResponse(**source.model_dump()) for source in sources],
            total=len(sources),
        )

    def run_source_import(self, source_id: str) -> dict[str, Any]:
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise KeyError("Saved source not found.")
        started_at = datetime.now(timezone.utc)
        try:
            result = self._run_import(source.connector_type, source.path, source.config)
            failed_count = int(getattr(result, "failed_count", 0))
            imported_count = int(getattr(result, "imported_count", 0))
            status = "failed" if imported_count == 0 and failed_count > 0 else "partial" if failed_count > 0 else "success"
            result_json = result.model_dump(mode="json")
            message = getattr(result, "message", "Import completed.")
        except Exception as exc:
            status = "failed"
            result_json = {"error": str(exc)}
            message = str(exc)
            imported_count = 0
            failed_count = 1
            result = None

        completed_at = datetime.now(timezone.utc)
        skipped_count = int(result_json.get("skipped_count", 0)) if isinstance(result_json, dict) else 0
        run = self._source_repository.create_import_run(
            {
                "source_id": source.id,
                "connector_type": source.connector_type,
                "path": source.path,
                "status": status,
                "imported_count": imported_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "message": message,
                "result_json": result_json,
                "started_at": started_at,
                "completed_at": completed_at,
            }
        )
        self._source_repository.update_last_import(source.id, status, message, completed_at)
        refreshed = self._source_repository.get_source(source.id) or source
        return {
            "source": ConnectorSourceResponse(**refreshed.model_dump()),
            "import_run": ImportRunResponse(**run.model_dump()),
            "result": result_json,
        }

    def list_import_runs(
        self,
        source_id: str | None = None,
        connector_type: str | None = None,
        limit: int = 20,
    ) -> ImportRunsResponse:
        runs = self._source_repository.list_import_runs(source_id=source_id, connector_type=connector_type, limit=limit)
        return ImportRunsResponse(runs=[ImportRunResponse(**run.model_dump()) for run in runs], total=len(runs))

    def clear_source_events(self, source_id: str) -> dict[str, object]:
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise KeyError("Saved source not found.")
        event_ids = [event.id for event in self._event_repository.list_all_events(include_hidden=True) if self._matches_source_event(source.connector_type, source.path, event)]
        deleted_relationships = self._relationship_repository.delete_relationships_for_event_ids(event_ids)
        try:
            from app.integrations.vector_store.chroma_vector_store import chroma_vector_store

            for event_id in event_ids:
                chroma_vector_store.delete_event(event_id)
        except Exception:
            pass
        deleted_events = self._event_repository.delete_events_by_ids(event_ids)
        return {"status": "cleared", "deleted_events": deleted_events, "deleted_relationships": deleted_relationships}

    def count_sources(self) -> int:
        return self._source_repository.count_sources()

    def count_import_runs(self) -> int:
        return self._source_repository.count_import_runs()

    def clear_import_runs(self) -> int:
        return self._source_repository.clear_import_runs()

    def clear_sources(self) -> int:
        return self._source_repository.clear_sources()

    def _run_import(self, connector_type: str, path: str, config: dict[str, Any]):
        if connector_type == "file_system":
            return self._file_import_service.import_folder(
                FileImportRequest(
                    folder_path=path,
                    recursive=bool(config.get("recursive", True)),
                    max_files=int(config.get("max_files", 100)),
                    max_file_size_kb=int(config.get("max_file_size_kb", 256)),
                    allowed_extensions=config.get("allowed_extensions"),
                )
            )
        if connector_type == "logs":
            return self._log_import_service.import_log(
                LogImportRequest(
                    file_path=path,
                    max_lines=int(config.get("max_lines", 1000)),
                    only_errors=bool(config.get("only_errors", False)),
                    group_similar=bool(config.get("group_similar", True)),
                )
            )
        if connector_type == "git":
            return self._git_import_service.import_repo(
                GitImportRequest(
                    repo_path=path,
                    max_commits=int(config.get("max_commits", 50)),
                    include_diff_summary=bool(config.get("include_diff_summary", True)),
                    include_status=bool(config.get("include_status", True)),
                )
            )
        raise ValueError("Unsupported connector type.")

    def _matches_source_event(self, connector_type: str, path: str, event) -> bool:
        metadata = event.metadata or {}
        if connector_type == "file_system":
            return event.source.value == "file_system" and (
                metadata.get("path") == path or str(metadata.get("path", "")).startswith(path)
            )
        if connector_type == "logs":
            return event.source.value == "logs" and metadata.get("file_path") == path
        if connector_type == "git":
            return event.source.value == "git" and (metadata.get("repo_path") == path or metadata.get("repo_root") == path)
        return False


connector_source_service = ConnectorSourceService()
