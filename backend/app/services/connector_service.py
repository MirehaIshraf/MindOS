from app.schemas.connectors import ConnectorListResponse
from app.services.connector_registry_service import connector_registry_service


class ConnectorService:
    """Compatibility wrapper around the unified connector registry."""

    def list_connectors(self) -> ConnectorListResponse:
        return connector_registry_service.list_connectors()
