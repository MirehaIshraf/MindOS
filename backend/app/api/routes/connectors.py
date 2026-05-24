from fastapi import APIRouter

from app.services.connector_service import ConnectorService

router = APIRouter(prefix="/connectors", tags=["connectors"])
service = ConnectorService()


@router.get("")
def connectors_placeholder() -> dict[str, str]:
    return service.placeholder()
