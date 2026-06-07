from app.domain.models import Playbook, SkillStep
from app.repositories.base import PlaybookRepository


class MemoryPlaybookRepository(PlaybookRepository):
    def __init__(self) -> None:
        self._playbooks: dict[str, Playbook] = {}

    def add(self, playbook: Playbook) -> Playbook:
        self._playbooks[playbook.id] = playbook
        return playbook

    def create(self, name: str, description: str = "", steps: list[SkillStep] | None = None) -> Playbook:
        return self.add(Playbook(name=name, description=description, steps=steps or []))

    def list(self) -> list[Playbook]:
        return list(self._playbooks.values())

    def get(self, playbook_id: str) -> Playbook | None:
        return self._playbooks.get(playbook_id)

    def update(self, playbook_id: str, updates: dict) -> Playbook | None:
        playbook = self._playbooks.get(playbook_id)
        if playbook is None:
            return None
        updated = playbook.model_copy(update=updates)
        self._playbooks[playbook_id] = updated
        return updated

    def delete(self, playbook_id: str) -> bool:
        return self._playbooks.pop(playbook_id, None) is not None

    def clear(self) -> None:
        self._playbooks.clear()

    def count(self) -> int:
        return len(self._playbooks)


memory_playbook_repository = MemoryPlaybookRepository()


def get_memory_playbook_repository() -> MemoryPlaybookRepository:
    return memory_playbook_repository
