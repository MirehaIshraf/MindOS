import logging
from datetime import datetime, timezone

from app.core.dependencies import get_playbook_repository
from app.domain.models import Playbook, SkillStep
from app.repositories.base import PlaybookRepository
from app.schemas.playbooks import (
    PlaybookCreateRequest,
    PlaybookListResponse,
    PlaybookResponse,
    PlaybookRunResponse,
    RecordStartResponse,
    RecordStopResponse,
)
from app.services import observation_service
from app.services.skill_file_generator_service import generate_skill_steps
from app.services.playbook_execution_service import execute as execute_playbook

logger = logging.getLogger(__name__)


class PlaybookService:
    def __init__(self, repo: PlaybookRepository | None = None) -> None:
        self._repo = repo or get_playbook_repository()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_playbooks(self) -> PlaybookListResponse:
        playbooks = self._repo.list()
        return PlaybookListResponse(playbooks=playbooks)

    def get_playbook(self, playbook_id: str) -> PlaybookResponse:
        playbook = self._repo.get(playbook_id)
        if playbook is None:
            raise KeyError(f"Playbook {playbook_id!r} not found")
        return PlaybookResponse(playbook=playbook)

    def create_playbook(self, request: PlaybookCreateRequest) -> PlaybookResponse:
        playbook = self._repo.add(
            Playbook(
                name=request.name,
                description=request.description,
                steps=request.steps,
            )
        )
        logger.info("Created playbook %s (%d steps)", playbook.id, len(playbook.steps))
        return PlaybookResponse(playbook=playbook)

    def delete_playbook(self, playbook_id: str) -> dict:
        deleted = self._repo.delete(playbook_id)
        if not deleted:
            raise KeyError(f"Playbook {playbook_id!r} not found")
        return {"deleted": playbook_id}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def start_recording(self) -> RecordStartResponse:
        session_id = observation_service.start_recording()
        return RecordStartResponse(session_id=session_id, status="recording")

    def stop_recording(self) -> RecordStopResponse:
        session_id, raw_events = observation_service.stop_recording()
        steps = generate_skill_steps(raw_events)
        return RecordStopResponse(
            session_id=session_id,
            steps=steps,
            step_count=len(steps),
        )

    def is_recording(self) -> bool:
        return observation_service.is_recording()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_playbook(self, playbook_id: str, confirm_step: int | None = None) -> PlaybookRunResponse:
        playbook = self._repo.get(playbook_id)
        if playbook is None:
            raise KeyError(f"Playbook {playbook_id!r} not found")

        result = execute_playbook(playbook_id, playbook.steps, confirm_step=confirm_step)

        # Update run stats if completed (not paused mid-way)
        if result.status in ("completed", "failed"):
            self._repo.update(playbook_id, {
                "run_count": playbook.run_count + 1,
                "last_run_at": datetime.now(timezone.utc),
            })

        return PlaybookRunResponse(
            playbook_id=playbook_id,
            status=result.status,
            steps_total=result.steps_total,
            steps_completed=result.steps_completed,
            steps_failed=result.steps_failed,
            log=[
                {
                    "step_index": sr.step_index,
                    "action": sr.action,
                    "description": sr.description,
                    "status": sr.status,
                    "message": sr.message,
                }
                for sr in result.log
            ],
        )


playbook_service = PlaybookService()
