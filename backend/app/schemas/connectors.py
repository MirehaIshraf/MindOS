from pydantic import BaseModel


class ConnectorStatus(BaseModel):
    name: str
    status: str


class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorStatus]
