from datetime import datetime, timezone

from app.domain.models import ConnectorSource, ImportRun
from app.repositories.base import ConnectorSourceRepository


class MemoryConnectorSourceRepository(ConnectorSourceRepository):
    def __init__(self) -> None:
        self._sources: dict[str, ConnectorSource] = {}
        self._runs: dict[str, ImportRun] = {}

    def create_source(self, data: dict) -> ConnectorSource:
        source = ConnectorSource(**data)
        self._sources[source.id] = source
        return source

    def update_source(self, source_id: str, data: dict) -> ConnectorSource:
        source = self._sources[source_id]
        updates = {key: value for key, value in data.items() if value is not None}
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = source.model_copy(update=updates)
        self._sources[source_id] = updated
        return updated

    def get_source(self, source_id: str) -> ConnectorSource | None:
        return self._sources.get(source_id)

    def list_sources(self, connector_type: str | None = None) -> list[ConnectorSource]:
        sources = list(self._sources.values())
        if connector_type:
            sources = [source for source in sources if source.connector_type == connector_type]
        return sorted(sources, key=lambda source: source.updated_at, reverse=True)

    def delete_source(self, source_id: str) -> bool:
        return self._sources.pop(source_id, None) is not None

    def update_last_import(self, source_id: str, status: str, message: str, completed_at) -> None:
        source = self._sources.get(source_id)
        if source is None:
            return
        self._sources[source_id] = source.model_copy(
            update={
                "last_import_at": completed_at,
                "last_import_status": status,
                "last_import_message": message,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def create_import_run(self, data: dict) -> ImportRun:
        run = ImportRun(**data)
        self._runs[run.id] = run
        return run

    def list_import_runs(
        self,
        source_id: str | None = None,
        connector_type: str | None = None,
        limit: int = 20,
    ) -> list[ImportRun]:
        runs = list(self._runs.values())
        if source_id:
            runs = [run for run in runs if run.source_id == source_id]
        if connector_type:
            runs = [run for run in runs if run.connector_type == connector_type]
        return sorted(runs, key=lambda run: run.started_at, reverse=True)[:limit]

    def count_sources(self) -> int:
        return len(self._sources)

    def count_import_runs(self) -> int:
        return len(self._runs)

    def clear_import_runs(self) -> int:
        count = len(self._runs)
        self._runs.clear()
        return count

    def clear_sources(self) -> int:
        count = len(self._sources)
        self._sources.clear()
        return count


memory_connector_source_repository = MemoryConnectorSourceRepository()


def get_memory_connector_source_repository() -> MemoryConnectorSourceRepository:
    return memory_connector_source_repository
