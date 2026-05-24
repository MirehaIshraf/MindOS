from pydantic import BaseModel, Field

from app.domain.models import Playbook


class PlaybookCreateRequest(BaseModel):
    name: str
    description: str
    steps: list[str] = Field(default_factory=list)


class PlaybookResponse(BaseModel):
    playbook: Playbook


class PlaybookListResponse(BaseModel):
    playbooks: list[Playbook]
