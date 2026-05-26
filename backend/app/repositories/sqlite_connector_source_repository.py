from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.core.database import ConnectorSourceRecord, ImportRunRecord, get_session_factory, initialize_database
from app.domain.models import ConnectorSource, ImportRun
from app.repositories.base import ConnectorSourceRepository
from app.repositories.sqlite_utils import dumps_json, loads_json


class SQLiteConnectorSourceRepository(ConnectorSourceRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

    def create_source(self, data: dict) -> ConnectorSource:
        source = ConnectorSource(**data)
        with self._session_factory() as session:
            session.add(self._to_source_record(source))
            session.commit()
        return source

    def update_source(self, source_id: str, data: dict) -> ConnectorSource:
        with self._session_factory() as session:
            record = session.get(ConnectorSourceRecord, source_id)
            if record is None:
                raise KeyError(source_id)
            if "name" in data and data["name"] is not None:
                record.name = data["name"]
            if "path" in data and data["path"] is not None:
                record.path = data["path"]
            if "config" in data and data["config"] is not None:
                record.config_json = dumps_json(data["config"])
            if "enabled" in data and data["enabled"] is not None:
                record.enabled = bool(data["enabled"])
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._to_source(record)

    def get_source(self, source_id: str) -> ConnectorSource | None:
        with self._session_factory() as session:
            record = session.get(ConnectorSourceRecord, source_id)
            return self._to_source(record) if record else None

    def list_sources(self, connector_type: str | None = None) -> list[ConnectorSource]:
        with self._session_factory() as session:
            statement = select(ConnectorSourceRecord).order_by(ConnectorSourceRecord.updated_at.desc())
            if connector_type:
                statement = statement.where(ConnectorSourceRecord.connector_type == connector_type)
            records = session.scalars(statement).all()
            return [self._to_source(record) for record in records]

    def delete_source(self, source_id: str) -> bool:
        with self._session_factory() as session:
            result = session.execute(delete(ConnectorSourceRecord).where(ConnectorSourceRecord.id == source_id))
            session.commit()
            return bool(result.rowcount)

    def update_last_import(self, source_id: str, status: str, message: str, completed_at) -> None:
        with self._session_factory() as session:
            record = session.get(ConnectorSourceRecord, source_id)
            if record is None:
                return
            record.last_import_at = completed_at
            record.last_import_status = status
            record.last_import_message = message
            record.updated_at = datetime.now(timezone.utc)
            session.commit()

    def create_import_run(self, data: dict) -> ImportRun:
        run = ImportRun(**data)
        with self._session_factory() as session:
            session.add(self._to_run_record(run))
            session.commit()
        return run

    def list_import_runs(
        self,
        source_id: str | None = None,
        connector_type: str | None = None,
        limit: int = 20,
    ) -> list[ImportRun]:
        with self._session_factory() as session:
            statement = select(ImportRunRecord).order_by(ImportRunRecord.started_at.desc()).limit(max(1, min(limit, 100)))
            if source_id:
                statement = statement.where(ImportRunRecord.source_id == source_id)
            if connector_type:
                statement = statement.where(ImportRunRecord.connector_type == connector_type)
            records = session.scalars(statement).all()
            return [self._to_run(record) for record in records]

    def count_sources(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(ConnectorSourceRecord)) or 0)

    def count_import_runs(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(ImportRunRecord)) or 0)

    def clear_import_runs(self) -> int:
        with self._session_factory() as session:
            result = session.execute(delete(ImportRunRecord))
            session.commit()
            return int(result.rowcount or 0)

    def clear_sources(self) -> int:
        with self._session_factory() as session:
            result = session.execute(delete(ConnectorSourceRecord))
            session.commit()
            return int(result.rowcount or 0)

    def _to_source_record(self, source: ConnectorSource) -> ConnectorSourceRecord:
        return ConnectorSourceRecord(
            id=source.id,
            connector_type=source.connector_type,
            name=source.name,
            path=source.path,
            config_json=dumps_json(source.config),
            enabled=source.enabled,
            created_at=source.created_at,
            updated_at=source.updated_at,
            last_import_at=source.last_import_at,
            last_import_status=source.last_import_status,
            last_import_message=source.last_import_message,
        )

    def _to_source(self, record: ConnectorSourceRecord) -> ConnectorSource:
        return ConnectorSource(
            id=record.id,
            connector_type=record.connector_type,
            name=record.name,
            path=record.path,
            config=loads_json(record.config_json, {}),
            enabled=record.enabled,
            created_at=record.created_at,
            updated_at=record.updated_at,
            last_import_at=record.last_import_at,
            last_import_status=record.last_import_status,
            last_import_message=record.last_import_message,
        )

    def _to_run_record(self, run: ImportRun) -> ImportRunRecord:
        return ImportRunRecord(
            id=run.id,
            source_id=run.source_id,
            connector_type=run.connector_type,
            path=run.path,
            status=run.status,
            imported_count=run.imported_count,
            skipped_count=run.skipped_count,
            failed_count=run.failed_count,
            message=run.message,
            result_json=dumps_json(run.result_json),
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

    def _to_run(self, record: ImportRunRecord) -> ImportRun:
        return ImportRun(
            id=record.id,
            source_id=record.source_id,
            connector_type=record.connector_type,
            path=record.path,
            status=record.status,
            imported_count=record.imported_count,
            skipped_count=record.skipped_count,
            failed_count=record.failed_count,
            message=record.message or "",
            result_json=loads_json(record.result_json, {}),
            started_at=record.started_at,
            completed_at=record.completed_at,
        )
