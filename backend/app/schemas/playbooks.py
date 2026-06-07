from pydantic import BaseModel, Field

from app.domain.models import Playbook, SkillStep


class PlaybookCreateRequest(BaseModel):
    name: str
    description: str = ""
    steps: list[SkillStep] = Field(default_factory=list)
    raw_timeline: str = ""   # optional raw event timeline for debugging


class PlaybookResponse(BaseModel):
    playbook: Playbook


class PlaybookListResponse(BaseModel):
    playbooks: list[Playbook]


class RecordStartResponse(BaseModel):
    session_id: str
    status: str = "recording"


class RecordStopResponse(BaseModel):
    session_id: str
    steps: list[SkillStep]
    step_count: int


class PlaybookRunResponse(BaseModel):
    playbook_id: str
    status: str
    steps_total: int
    steps_completed: int
    steps_failed: int
    log: list[dict]
