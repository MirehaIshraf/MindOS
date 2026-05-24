from typing import Any

from app.domain.enums import PermissionLevel
from app.integrations.tools.base import Tool


class MockEmailTool(Tool):
    @property
    def name(self) -> str:
        return "mock_email"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.write_with_confirmation

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        params = kwargs.get("params", kwargs)
        return {
            "mock": True,
            "status": "drafted",
            "message": "Mock email prepared. No real email was sent.",
            "to": params.get("recipient", ""),
            "subject": params.get("subject", ""),
        }
