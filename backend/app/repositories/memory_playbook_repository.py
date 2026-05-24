from app.domain.models import Playbook
from app.repositories.base import PlaybookRepository


class MemoryPlaybookRepository(PlaybookRepository):
    def __init__(self) -> None:
        self._playbooks: dict[str, Playbook] = {}

    def add(self, playbook: Playbook) -> Playbook:
        self._playbooks[playbook.id] = playbook
        return playbook

    def list(self) -> list[Playbook]:
        return list(self._playbooks.values())

    def get(self, playbook_id: str) -> Playbook | None:
        return self._playbooks.get(playbook_id)
