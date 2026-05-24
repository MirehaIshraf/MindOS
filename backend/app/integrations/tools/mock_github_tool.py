from typing import Any

from app.domain.enums import PermissionLevel
from app.integrations.tools.base import Tool


class MockGitHubTool(Tool):
    @property
    def name(self) -> str:
        return "mock_github"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.write_with_confirmation

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "mock": True,
            "status": "prepared",
            "pr_number": 42,
            "message": "Mock pull request prepared. No real GitHub API was called.",
        }
