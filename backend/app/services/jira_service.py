import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas.jira import (
    DEFAULT_JIRA_ISSUE_TYPE,
    JiraConfigRequest,
    JiraConnectionResponse,
    JiraIssue,
    JiraIssueCreateRequest,
    JiraIssueCreateResponse,
    JiraIssueSearchRequest,
    JiraIssueSearchResponse,
    JiraProject,
    JiraProjectsResponse,
    JiraStatusResponse,
    JiraTestResponse,
)
from app.services.connector_registry_service import connector_registry_service


class JiraConnectorError(ValueError):
    pass


class JiraService:
    def status(self) -> JiraStatusResponse:
        config = self._config()
        heartbeat = connector_registry_service.heartbeat_metadata("jira")
        enabled = connector_registry_service.is_enabled("jira")
        configured = self._configured(config)
        connected = bool(enabled and configured and heartbeat.get("display_name") and not heartbeat.get("last_error"))
        if connected:
            status = "connected"
        elif heartbeat.get("last_error"):
            status = "error"
        elif configured:
            status = "configured"
        else:
            status = "needs_configuration" if enabled else "off"
        return JiraStatusResponse(
            enabled=enabled,
            configured=configured,
            connected=connected,
            status=status,
            site_url=str(config.get("site_url") or "") or None,
            email=str(config.get("email") or "") or None,
            has_api_token=bool(config.get("api_token")),
            default_project_key=str(config.get("default_project_key") or "") or None,
            default_issue_type=str(config.get("default_issue_type") or DEFAULT_JIRA_ISSUE_TYPE),
            last_tested_at=str(heartbeat.get("last_tested_at") or "") or None,
            last_error=str(heartbeat.get("last_error") or "") or None,
            display_name=str(heartbeat.get("display_name") or "") or None,
            account_id=str(heartbeat.get("account_id") or "") or None,
            project_count=int(heartbeat.get("project_count") or 0),
        )

    def save_config(self, request: JiraConfigRequest) -> JiraStatusResponse:
        next_config = {
            "site_url": request.site_url,
            "email": request.email,
            "api_token": request.api_token,
            "default_project_key": request.default_project_key,
            "default_issue_type": request.default_issue_type or DEFAULT_JIRA_ISSUE_TYPE,
        }
        connector_registry_service.save_config("jira", next_config)
        connector_registry_service.record_seen(
            "jira",
            {
                "display_name": None,
                "account_id": None,
                "project_count": 0,
                "last_tested_at": None,
                "last_error": None,
            },
        )
        connector_registry_service.set_enabled("jira", False)
        return self.status()

    def test_connection(self) -> JiraTestResponse:
        myself = self._request("GET", "/rest/api/3/myself")
        projects = self._fetch_projects()
        display_name = str(myself.get("displayName") or myself.get("emailAddress") or "")
        account_id = str(myself.get("accountId") or "") or None
        connector_registry_service.set_enabled("jira", True)
        connector_registry_service.record_seen(
            "jira",
            {
                "display_name": display_name,
                "account_id": account_id,
                "project_count": len(projects),
                "last_tested_at": datetime.now(timezone.utc).isoformat(),
                "last_error": None,
            },
        )
        return JiraTestResponse(
            ok=True,
            connected=True,
            display_name=display_name or None,
            account_id=account_id,
            project_count=len(projects),
            projects=projects,
            message=f"Connected to Jira as {display_name or 'your Atlassian account'}.",
        )

    def connect(self) -> JiraConnectionResponse:
        test = self.test_connection()
        return JiraConnectionResponse(
            status="connected",
            connected=True,
            message=test.message,
            connector=self.status(),
        )

    def disconnect(self) -> JiraConnectionResponse:
        connector_registry_service.set_enabled("jira", False)
        return JiraConnectionResponse(
            status="disconnected",
            connected=False,
            message="Jira connector disconnected. Saved credentials remain local.",
            connector=self.status(),
        )

    def remove_credentials(self) -> JiraStatusResponse:
        connector_registry_service.save_config("jira", {})
        connector_registry_service.set_enabled("jira", False)
        connector_registry_service.record_seen(
            "jira",
            {
                "display_name": None,
                "account_id": None,
                "project_count": 0,
                "last_tested_at": None,
                "last_error": None,
            },
        )
        return self.status()

    def list_projects(self) -> JiraProjectsResponse:
        self._require_connected()
        projects = self._fetch_projects()
        connector_registry_service.record_seen("jira", {"project_count": len(projects), "last_error": None})
        return JiraProjectsResponse(projects=projects, total=len(projects))

    def search_issues(self, request: JiraIssueSearchRequest) -> JiraIssueSearchResponse:
        self._require_connected()
        jql = self._build_search_jql(request.query, request.project_key)
        payload = self._request(
            "POST",
            "/rest/api/3/search",
            json_body={
                "jql": jql,
                "maxResults": min(max(request.max_results, 1), 20),
                "fields": ["summary", "status", "issuetype", "updated"],
            },
        )
        raw_issues = payload.get("issues") if isinstance(payload, dict) else []
        issues: list[JiraIssue] = []
        for item in raw_issues if isinstance(raw_issues, list) else []:
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            key = str(item.get("key") or "")
            if not key:
                continue
            status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
            issue_type = fields.get("issuetype") if isinstance(fields.get("issuetype"), dict) else {}
            issues.append(
                JiraIssue(
                    key=key,
                    summary=str(fields.get("summary") or ""),
                    status=str(status.get("name") or ""),
                    issue_type=str(issue_type.get("name") or ""),
                    updated=str(fields.get("updated") or "") or None,
                    url=self._issue_url(key),
                )
            )
        return JiraIssueSearchResponse(ok=True, issues=issues)

    def create_issue(self, request: JiraIssueCreateRequest) -> JiraIssueCreateResponse:
        self._require_connected()
        if request.confirmation is not True:
            raise JiraConnectorError("Explicit confirmation is required before creating a Jira issue.")
        fields: dict[str, Any] = {
            "project": {"key": request.project_key},
            "issuetype": {"name": request.issue_type},
            "summary": request.summary,
            "description": self._plain_text_to_adf(request.description),
        }
        if request.labels:
            fields["labels"] = request.labels
        if request.priority:
            fields["priority"] = {"name": request.priority.strip()}
        payload = self._request("POST", "/rest/api/3/issue", json_body={"fields": fields})
        issue_key = str(payload.get("key") or "")
        if not issue_key:
            raise JiraConnectorError("Jira created an issue but did not return an issue key.")
        return JiraIssueCreateResponse(ok=True, issue_key=issue_key, url=self._issue_url(issue_key))

    def _fetch_projects(self) -> list[JiraProject]:
        payload = self._request("GET", "/rest/api/3/project/search", params={"maxResults": 100})
        values = payload.get("values") if isinstance(payload, dict) else []
        projects: list[JiraProject] = []
        for item in values if isinstance(values, list) else []:
            projects.append(
                JiraProject(
                    id=str(item.get("id") or ""),
                    key=str(item.get("key") or ""),
                    name=str(item.get("name") or ""),
                    project_type_key=item.get("projectTypeKey"),
                    simplified=item.get("simplified"),
                    style=item.get("style"),
                )
            )
        return [project for project in projects if project.key]

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        config = self._config()
        if not self._configured(config):
            raise JiraConnectorError("Jira connector is not configured.")
        site_url = str(config.get("site_url") or "").rstrip("/")
        auth = base64.b64encode(f"{config.get('email')}:{config.get('api_token')}".encode("utf-8")).decode("ascii")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
            "User-Agent": "MindOS",
        }
        try:
            with httpx.Client(base_url=site_url, headers=headers, timeout=30, follow_redirects=True) as client:
                response = client.request(method, path, params=params, json=json_body)
        except httpx.RequestError as error:
            self._record_error("Invalid Jira site URL, email, or API token.")
            raise JiraConnectorError("Invalid Jira site URL, email, or API token.") from error

        if response.status_code in {401, 403}:
            self._record_error("Invalid Jira site URL, email, or API token.")
            raise JiraConnectorError("Invalid Jira site URL, email, or API token.")
        if response.status_code == 404:
            self._record_error("Invalid Jira site URL, email, or API token.")
            raise JiraConnectorError("Invalid Jira site URL, email, or API token.")
        if response.status_code == 429:
            self._record_error("Jira rate limit reached. Try again later.")
            raise JiraConnectorError("Jira rate limit reached. Try again later.")
        if response.status_code >= 400:
            self._record_error("Jira connection failed. Check your site URL, email, and API token.")
            raise JiraConnectorError("Jira connection failed. Check your site URL, email, and API token.")
        try:
            return response.json()
        except ValueError as error:
            self._record_error("Jira returned an unexpected response.")
            raise JiraConnectorError("Jira returned an unexpected response.") from error

    def _require_connected(self) -> None:
        status = self.status()
        if not status.connected:
            raise JiraConnectorError("Jira connector is not connected.")

    def _record_error(self, message: str) -> None:
        connector_registry_service.record_seen(
            "jira",
            {
                "last_error": message,
                "last_tested_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _config(self) -> dict[str, Any]:
        return connector_registry_service.get_config_dict("jira")

    def _configured(self, config: dict[str, Any]) -> bool:
        return bool(config.get("site_url") and config.get("email") and config.get("api_token"))

    def _build_search_jql(self, query: str, project_key: str | None = None) -> str:
        escaped = self._escape_jql_text(query)
        clauses: list[str] = []
        if project_key:
            clean_project = "".join(char for char in project_key.upper() if char.isalnum() or char == "_")
            if clean_project:
                clauses.append(f"project = {clean_project}")
        clauses.append(f'text ~ "{escaped}"')
        return f"{' AND '.join(clauses)} ORDER BY updated DESC"

    def _escape_jql_text(self, value: str) -> str:
        cleaned = "".join(char for char in value if char.isprintable())
        cleaned = cleaned.replace("\\", " ").replace('"', " ")
        cleaned = " ".join(cleaned.split())
        return cleaned[:200] or "issue"

    def _plain_text_to_adf(self, value: str) -> dict[str, Any]:
        paragraphs = [line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip()]
        if not paragraphs:
            paragraphs = ["No description provided."]
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": paragraph}],
                }
                for paragraph in paragraphs[:80]
            ],
        }

    def _issue_url(self, key: str) -> str:
        site_url = str(self._config().get("site_url") or "").rstrip("/")
        return f"{site_url}/browse/{key}"


jira_service = JiraService()
