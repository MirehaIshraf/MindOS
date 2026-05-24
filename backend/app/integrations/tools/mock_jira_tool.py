from typing import Any

from app.domain.enums import PermissionLevel
from app.integrations.tools.base import Tool


class MockJiraTool(Tool):
    @property
    def name(self) -> str:
        return "mock_jira"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.write_with_confirmation

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "mock": True,
            "status": "created",
            "ticket_id": "MOCK-123",
            "message": "Mock Jira ticket created. No real Jira API was called.",
        }
