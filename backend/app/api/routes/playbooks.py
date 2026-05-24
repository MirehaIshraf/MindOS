from fastapi import APIRouter

from app.services.playbook_service import PlaybookService

router = APIRouter(prefix="/playbooks", tags=["playbooks"])
service = PlaybookService()


@router.get("")
def playbooks_placeholder() -> dict[str, str]:
    return service.placeholder()
