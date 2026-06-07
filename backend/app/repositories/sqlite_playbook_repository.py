import json
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.core.database import PlaybookRecord, get_session_factory, initialize_database
from app.domain.models import Playbook, SkillStep
from app.repositories.base import PlaybookRepository


def _serialize_steps(steps: list[SkillStep]) -> str:
    return json.dumps([s.model_dump() for s in steps])


def _deserialize_steps(raw: str | None) -> list[SkillStep]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [SkillStep(**item) for item in data]
    except Exception:
        return []


class SQLitePlaybookRepository(PlaybookRepository):
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()

    def add(self, playbook: Playbook) -> Playbook:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            session.add(
                PlaybookRecord(
                    id=playbook.id,
                    name=playbook.name,
                    description=playbook.description,
                    trigger_phrases_json="[]",
                    steps_json=_serialize_steps(playbook.steps),
                    run_count=0,
                    last_run_at=None,
                    created_at=playbook.created_at,
                    updated_at=now,
                )
            )
            session.commit()
        return playbook

    def create(self, name: str, description: str = "", steps: list[SkillStep] | None = None) -> Playbook:
        return self.add(Playbook(name=name, description=description, steps=steps or []))

    def list(self) -> list[Playbook]:
        with self._session_factory() as session:
            records = session.scalars(select(PlaybookRecord).order_by(PlaybookRecord.created_at.desc())).all()
            return [self._to_playbook(record) for record in records]

    def get(self, playbook_id: str) -> Playbook | None:
        with self._session_factory() as session:
            record = session.get(PlaybookRecord, playbook_id)
            return self._to_playbook(record) if record else None

    def update(self, playbook_id: str, updates: dict) -> Playbook | None:
        with self._session_factory() as session:
            record = session.get(PlaybookRecord, playbook_id)
            if record is None:
                return None
            if "name" in updates:
                record.name = updates["name"]
            if "description" in updates:
                record.description = updates["description"]
            if "steps" in updates:
                record.steps_json = _serialize_steps(updates["steps"])
            if "run_count" in updates:
                record.run_count = updates["run_count"]
            if "last_run_at" in updates:
                record.last_run_at = updates["last_run_at"]
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._to_playbook(record)

    def delete(self, playbook_id: str) -> bool:
        with self._session_factory() as session:
            record = session.get(PlaybookRecord, playbook_id)
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def clear(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(PlaybookRecord))
            session.commit()

    def count(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(PlaybookRecord)) or 0)

    def _to_playbook(self, record: PlaybookRecord) -> Playbook:
        return Playbook(
            id=record.id,
            name=record.name,
            description=record.description or "",
            steps=_deserialize_steps(record.steps_json),
            run_count=record.run_count or 0,
            last_run_at=record.last_run_at,
            created_at=record.created_at,
        )
