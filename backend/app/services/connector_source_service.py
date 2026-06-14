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
from app.schemas.file_index import (
    DEFAULT_FILE_INDEX_EXTENSIONS,
    TrackedFolderCreateRequest,
    TrackedFolderResponse,
    TrackedFoldersResponse,
    TrackedFolderUpdateRequest,
)
from app.services.file_import_service import FileImportService
from app.services.file_index_service import FileIndexService
from app.services.file_snapshot_service import validate_root_path
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
        self._file_index_service = FileIndexService(self._event_repository, self._source_repository)
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

    def list_tracked_folders(self) -> TrackedFoldersResponse:
        sources = self._source_repository.list_sources(connector_type="file_system")
        folders = [self._tracked_folder_response(source) for source in sources]
        return TrackedFoldersResponse(folders=folders, total=len(folders))

    def create_tracked_folder(self, request: TrackedFolderCreateRequest) -> TrackedFolderResponse:
        root = validate_root_path(request.path)
        normalized_path = str(root)
        existing = self._find_file_source_by_path(normalized_path)
        config = self._tracked_folder_config(request.model_dump(), include_defaults=True)
        if existing:
            source = self._source_repository.update_source(
                existing.id,
                {
                    "name": request.name.strip() if request.name else existing.name,
                    "path": normalized_path,
                    "config": {**(existing.config or {}), **config},
                    "enabled": request.enabled,
                },
            )
        else:
            source = self._source_repository.create_source(
                {
                    "connector_type": "file_system",
                    "name": request.name.strip() if request.name else root.name or normalized_path,
                    "path": normalized_path,
                    "config": config,
                    "enabled": request.enabled,
                }
            )
        return self._tracked_folder_response(source)

    def update_tracked_folder(self, source_id: str, request: TrackedFolderUpdateRequest) -> TrackedFolderResponse:
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise KeyError("Tracked folder not found.")
        if source.connector_type != "file_system":
            raise ValueError("Only File System tracked folders can be updated.")
        updates: dict[str, Any] = {}
        if request.path is not None:
            updates["path"] = str(validate_root_path(request.path))
        if request.name is not None:
            updates["name"] = request.name.strip() or source.name
        if request.enabled is not None:
            updates["enabled"] = request.enabled
        config_updates = self._tracked_folder_config(request.model_dump(exclude_unset=True), include_defaults=False)
        if config_updates:
            updates["config"] = {**(source.config or {}), **config_updates}
            updates["config"]["index_status"] = "idle"
            updates["config"]["next_index_after"] = None
        if not updates:
            return self._tracked_folder_response(source)
        updated = self._source_repository.update_source(source_id, updates)
        return self._tracked_folder_response(updated)

    def run_source_import(self, source_id: str) -> dict[str, Any]:
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise KeyError("Saved source not found.")
        started_at = datetime.now(timezone.utc)
        try:
            if source.connector_type == "file_system" and bool(source.config.get("indexing_enabled", False)):
                result = self._file_index_service.index_source(source.id)
                failed_count = int(getattr(result, "failed_count", 0))
                imported_count = int(getattr(result, "indexed_count", 0))
                skipped_count = int(getattr(result, "skipped_count", 0))
                status = "failed" if imported_count == 0 and failed_count > 0 else "partial" if failed_count > 0 else "success"
                result_json = result.model_dump(mode="json")
                message = getattr(result, "message", "Indexing completed.")
            else:
                result = self._run_import(source.connector_type, source.path, source.config)
                failed_count = int(getattr(result, "failed_count", 0))
                imported_count = int(getattr(result, "imported_count", 0))
                skipped_count = int(getattr(result, "skipped_count", 0))
                status = "failed" if imported_count == 0 and failed_count > 0 else "partial" if failed_count > 0 else "success"
                result_json = result.model_dump(mode="json")
                message = getattr(result, "message", "Import completed.")
        except Exception as exc:
            status = "failed"
            result_json = {"error": str(exc)}
            message = str(exc)
            imported_count = 0
            skipped_count = 0
            failed_count = 1
            result = None

        completed_at = datetime.now(timezone.utc)
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

    def index_source(self, source_id: str) -> dict[str, Any]:
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise KeyError("Saved source not found.")
        started_at = datetime.now(timezone.utc)
        try:
            result = self._file_index_service.index_source(source_id)
            status = "success" if result.failed_count == 0 else "partial"
            imported_count = result.indexed_count
            failed_count = result.failed_count
            skipped_count = result.skipped_count
            result_json = result.model_dump(mode="json")
            message = result.message
        except Exception as exc:
            status = "failed"
            imported_count = 0
            skipped_count = 0
            failed_count = 1
            result_json = {"error": str(exc)}
            message = str(exc)
        completed_at = datetime.now(timezone.utc)
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

    def tracked_folder(self, source_id: str) -> TrackedFolderResponse:
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise KeyError("Tracked folder not found.")
        if source.connector_type != "file_system":
            raise ValueError("Only File System sources are tracked folders.")
        return self._tracked_folder_response(source)

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
        event_ids = [event.id for event in self._event_repository.list_all_events(include_hidden=True) if self._matches_source_event(source, event)]
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

    def _matches_source_event(self, source, event) -> bool:
        metadata = event.metadata or {}
        connector_type = source.connector_type
        path = source.path
        if connector_type == "file_system":
            return event.source.value == "file_system" and (
                metadata.get("source_id") == source.id
                or metadata.get("path") == path
                or str(metadata.get("path", "")).startswith(path)
            )
        if connector_type == "logs":
            return event.source.value == "logs" and metadata.get("file_path") == path
        if connector_type == "git":
            return event.source.value == "git" and (metadata.get("repo_path") == path or metadata.get("repo_root") == path)
        return False

    def _find_file_source_by_path(self, path: str):
        for source in self._source_repository.list_sources(connector_type="file_system"):
            try:
                if str(validate_root_path(source.path)) == path:
                    return source
            except ValueError:
                if source.path == path:
                    return source
        return None

    def _tracked_folder_config(self, values: dict[str, Any], include_defaults: bool = True) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if "indexing_enabled" in values:
            config["indexing_enabled"] = bool(values["indexing_enabled"])
        if "recursive" in values:
            config["recursive"] = bool(values["recursive"])
        if "max_depth" in values and values["max_depth"] is not None:
            config["max_depth"] = max(0, min(int(values["max_depth"]), 10))
        if "max_files" in values and values["max_files"] is not None:
            config["max_files"] = max(1, min(int(values["max_files"]), 5000))
        if "max_file_size_mb" in values and values["max_file_size_mb"] is not None:
            config["max_file_size_mb"] = max(1, min(int(values["max_file_size_mb"]), 25))
        if "include_hidden" in values:
            config["include_hidden"] = bool(values["include_hidden"])
        if "allowed_extensions" in values and values["allowed_extensions"] is not None:
            config["allowed_extensions"] = values["allowed_extensions"] or list(DEFAULT_FILE_INDEX_EXTENSIONS)
            config["include_patterns"] = config["allowed_extensions"]
        if "exclude_patterns" in values and values["exclude_patterns"] is not None:
            config["exclude_patterns"] = values["exclude_patterns"]
        if "index_interval_minutes" in values and values["index_interval_minutes"] is not None:
            config["index_interval_minutes"] = max(10, min(int(values["index_interval_minutes"]), 30))
        if include_defaults:
            config.setdefault("indexing_enabled", True)
            config.setdefault("recursive", True)
            config.setdefault("max_depth", 5)
            config.setdefault("max_files", 2000)
            config.setdefault("max_file_size_mb", 5)
            config.setdefault("allowed_extensions", list(DEFAULT_FILE_INDEX_EXTENSIONS))
            config.setdefault("include_patterns", config["allowed_extensions"])
            config.setdefault("exclude_patterns", [])
            config.setdefault("index_interval_minutes", 20)
            config.setdefault("index_status", "idle")
            config.setdefault("next_index_after", None)
            config.setdefault("missing_count", 0)
        return config

    def _tracked_folder_response(self, source) -> TrackedFolderResponse:
        config = source.config or {}
        return TrackedFolderResponse(
            id=source.id,
            name=source.name,
            path=source.path,
            enabled=source.enabled,
            indexing_enabled=bool(config.get("indexing_enabled", True)),
            index_status=str(config.get("index_status") or "idle"),
            last_indexed_at=config.get("last_indexed_at"),
            next_index_after=config.get("next_index_after"),
            last_error=config.get("last_error"),
            file_count=int(config.get("file_count") or 0),
            indexed_count=int(config.get("indexed_count") or 0),
            inventory_count=int(config.get("inventory_count") or config.get("file_count") or 0),
            content_failed_count=int(config.get("content_failed_count") or 0),
            skipped_count=int(config.get("skipped_count") or 0),
            missing_count=int(config.get("missing_count") or 0),
            config=config,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )


connector_source_service = ConnectorSourceService()
