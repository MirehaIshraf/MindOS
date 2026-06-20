from app.schemas.task_actions import ActionCapability, ActionCapabilityRegistry
from app.services.github_service import github_service
from app.services.gmail_service import gmail_service
from app.services.jira_service import jira_service


class TaskActionCapabilityService:
    def registry(self) -> ActionCapabilityRegistry:
        gmail_status = gmail_service.status()
        github_status = github_service.status()
        jira_status = jira_service.status()

        gmail_draft_available = bool(gmail_status.connected and gmail_status.capabilities and gmail_status.capabilities.get("create_draft"))
        gmail_search_available = bool(gmail_status.connected and gmail_status.capabilities and gmail_status.capabilities.get("search_email"))
        gmail_send_available = bool(gmail_status.connected and gmail_status.capabilities and gmail_status.capabilities.get("send_email"))
        create_draft_available = gmail_draft_available
        draft_provider = "gmail"
        draft_reason = None
        if not create_draft_available:
            draft_reason = "Gmail is not connected. Open Connectors -> Gmail and connect it."
        send_reason = None
        if not gmail_status.connected:
            send_reason = "Gmail is not connected. Open Connectors -> Gmail and connect it."
        elif not gmail_status.capabilities.get("send_email") and gmail_status.capabilities.get("create_draft"):
            send_reason = "Gmail send is not connected yet. You can create a draft instead."
        elif not gmail_status.capabilities.get("send_email"):
            send_reason = "Gmail send capability was not detected."

        return ActionCapabilityRegistry(
            capabilities={
                "gmail.read": ActionCapability(
                    available=bool(gmail_status.connected),
                    provider="gmail",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None if gmail_status.connected else "Gmail is not connected. Open Connectors -> Gmail and connect it.",
                ),
                "gmail.createDraft": ActionCapability(
                    available=create_draft_available,
                    provider=draft_provider,
                    risk_level="medium",
                    requires_confirmation=True,
                    reason=draft_reason,
                ),
                "gmail.searchEmails": ActionCapability(
                    available=gmail_search_available,
                    provider="gmail",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None if gmail_search_available else "Gmail is not connected. Open Connectors -> Gmail and connect it.",
                ),
                "gmail.summarizeEmails": ActionCapability(
                    available=gmail_search_available,
                    provider="gmail",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None if gmail_search_available else "Gmail is not connected. Open Connectors -> Gmail and connect it.",
                ),
                "gmail.sendEmail": ActionCapability(
                    available=gmail_send_available,
                    provider="gmail",
                    risk_level="high",
                    requires_confirmation=True,
                    reason=send_reason,
                ),
                "gmail.send": ActionCapability(
                    available=gmail_send_available,
                    provider="gmail",
                    risk_level="high",
                    requires_confirmation=True,
                    reason=send_reason,
                ),
                "gmail.replyDraft": ActionCapability(
                    available=False,
                    provider="gmail",
                    risk_level="medium",
                    requires_confirmation=True,
                    reason="Gmail reply draft creation is not connected yet.",
                ),
                "github.read": ActionCapability(
                    available=bool(github_status.connected),
                    provider="github",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None if github_status.connected else "Connect GitHub first.",
                ),
                "github.createIssue": ActionCapability(
                    available=False,
                    provider="github",
                    risk_level="medium",
                    requires_confirmation=True,
                    reason="GitHub issue creation is not connected yet.",
                ),
                "github.createPullRequest": ActionCapability(
                    available=False,
                    provider="github",
                    risk_level="medium",
                    requires_confirmation=True,
                    reason="GitHub pull request creation is not connected yet.",
                ),
                "jira.read": ActionCapability(
                    available=bool(jira_status.connected),
                    provider="jira",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None if jira_status.connected else "Connect Jira first.",
                ),
                "jira.searchIssues": ActionCapability(
                    available=bool(jira_status.connected),
                    provider="jira",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None if jira_status.connected else "Connect Jira first.",
                ),
                "jira.createIssue": ActionCapability(
                    available=bool(jira_status.connected),
                    provider="jira",
                    risk_level="medium",
                    requires_confirmation=True,
                    reason=None if jira_status.connected else "Connect Jira first.",
                ),
                "git.status": ActionCapability(
                    available=True,
                    provider="local_git",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None,
                ),
                "git.diff": ActionCapability(
                    available=True,
                    provider="local_git",
                    risk_level="safe",
                    requires_confirmation=False,
                    reason=None,
                ),
                "git.commit": ActionCapability(
                    available=False,
                    provider="local_git",
                    risk_level="medium",
                    requires_confirmation=True,
                    reason="Local Git commit execution is not connected yet.",
                ),
                "git.push": ActionCapability(
                    available=False,
                    provider="local_git",
                    risk_level="high",
                    requires_confirmation=True,
                    reason="Git push execution is not connected yet.",
                ),
            }
        )


task_action_capability_service = TaskActionCapabilityService()
