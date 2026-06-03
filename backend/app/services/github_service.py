from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus, EventSource
from app.repositories.base import EventRepository
from app.schemas.github import (
    GitHubConfigRequest,
    GitHubRepo,
    GitHubReposResponse,
    GitHubSelectionRequest,
    GitHubStatusResponse,
    GitHubSyncRequest,
    GitHubSyncResponse,
    GitHubTestResponse,
)
from app.services.connector_registry_service import connector_registry_service
from app.services.relationship_service import relationship_service


DEFAULT_API_BASE_URL = "https://api.github.com"


class GitHubConnectorError(ValueError):
    pass


class GitHubService:
    def __init__(self, events: EventRepository | None = None) -> None:
        self._events = events or get_event_repository()

    def status(self) -> GitHubStatusResponse:
        config = self._config()
        enabled = connector_registry_service.is_enabled("github")
        heartbeat = connector_registry_service.heartbeat_metadata("github")
        selected_repos = list(config.get("selected_repos") or [])
        event_count = len([event for event in self._events.list_all_events(include_hidden=True) if event.source.value == "github"])
        return GitHubStatusResponse(
            enabled=enabled,
            configured=bool(config.get("token")),
            connected=bool(enabled and config.get("token") and heartbeat.get("username")),
            status=connector_registry_service.get_connector("github").status,
            username=str(heartbeat.get("username") or "") or None,
            api_base_url=str(config.get("api_base_url") or DEFAULT_API_BASE_URL),
            last_sync_at=str(heartbeat.get("last_sync_at") or "") or None,
            last_error=str(heartbeat.get("last_error") or "") or None,
            repo_count=len(selected_repos),
            event_count=event_count,
            selected_repos=selected_repos,
            selected_repositories=selected_repos,
            sync_settings={**_default_sync_settings(), **dict(config.get("sync_settings") or {})},
        )

    def save_config(self, request: GitHubConfigRequest) -> GitHubStatusResponse:
        current = self._config()
        token = (request.token or "").strip()
        next_config = {
            **current,
            "api_base_url": request.api_base_url.strip().rstrip("/") or DEFAULT_API_BASE_URL,
        }
        if token:
            next_config["token"] = token
            next_config.pop("selected_repos", None)
            next_config.pop("sync_settings", None)
        elif request.token is not None:
            next_config.pop("token", None)
            next_config.pop("selected_repos", None)
            next_config.pop("sync_settings", None)
        connector_registry_service.save_config("github", next_config)
        if request.token is not None and not token:
            connector_registry_service.set_enabled("github", False)
        heartbeat_update = {"last_error": None}
        if request.token is not None:
            heartbeat_update.update({"username": None, "selected_repos": [], "repo_count": 0, "repos_available_count": None})
        connector_registry_service.record_seen("github", heartbeat_update)
        return self.status()

    def test_connection(self) -> GitHubTestResponse:
        user = self._request("GET", "/user")
        username = str(user.get("login") or "")
        connector_registry_service.record_seen("github", {"username": username, "last_error": None})
        return GitHubTestResponse(
            status="connected",
            connected=True,
            username=username,
            message=f"Connected to GitHub as {username}.",
        )

    def list_repos(self) -> GitHubReposResponse:
        self._require_connected()
        repos = self._request("GET", "/user/repos", params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"})
        parsed: list[GitHubRepo] = []
        for repo in repos if isinstance(repos, list) else []:
            owner = repo.get("owner") or {}
            parsed.append(
                GitHubRepo(
                    full_name=str(repo.get("full_name") or ""),
                    name=str(repo.get("name") or ""),
                    owner=str(owner.get("login") or ""),
                    private=bool(repo.get("private")),
                    html_url=repo.get("html_url"),
                    updated_at=_parse_datetime(repo.get("updated_at")),
                    description=repo.get("description"),
                )
            )
        config = self._config()
        config["selected_repos"] = config.get("selected_repos") or []
        connector_registry_service.save_config("github", config)
        connector_registry_service.record_seen("github", {"repos_available_count": len(parsed), "last_error": None})
        return GitHubReposResponse(repos=parsed, total=len(parsed))

    def save_selection(self, request: GitHubSelectionRequest) -> GitHubStatusResponse:
        self._require_connected()
        config = self._config()
        config["selected_repos"] = request.repo_full_names
        config["sync_settings"] = {
            **_default_sync_settings(),
            **dict(config.get("sync_settings") or {}),
            **dict(request.sync_settings or {}),
        }
        connector_registry_service.save_config("github", config)
        connector_registry_service.record_seen(
            "github",
            {
                "selected_repos": request.repo_full_names,
                "repo_count": len(request.repo_full_names),
                "last_error": None,
            },
        )
        return self.status()

    def sync(self, request: GitHubSyncRequest) -> GitHubSyncResponse:
        self._require_connected()

        imported = 0
        updated = 0
        skipped = 0
        failed = 0
        created_ids: list[str] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}

        for repo in request.repo_full_names:
            repo_details = {"commits": 0, "issues": 0, "pull_requests": 0}
            try:
                if request.include_commits:
                    result = self._sync_commits(repo, request.max_items_per_type)
                    imported += result["created"]
                    updated += result["updated"]
                    created_ids.extend(result["ids"])
                    repo_details["commits"] = result["seen"]
                if request.include_issues:
                    result = self._sync_issues(repo, request.max_items_per_type)
                    imported += result["created"]
                    updated += result["updated"]
                    skipped += result["skipped"]
                    created_ids.extend(result["ids"])
                    repo_details["issues"] = result["seen"]
                if request.include_pull_requests:
                    result = self._sync_pull_requests(repo, request.max_items_per_type)
                    imported += result["created"]
                    updated += result["updated"]
                    created_ids.extend(result["ids"])
                    repo_details["pull_requests"] = result["seen"]
            except GitHubConnectorError as error:
                failed += 1
                warnings.append(f"{repo}: {error}")
            details[repo] = repo_details

        config = self._config()
        config["selected_repos"] = request.repo_full_names
        connector_registry_service.save_config("github", config)
        connector_registry_service.record_seen(
            "github",
            {
                "selected_repos": request.repo_full_names,
                "repo_count": len(request.repo_full_names),
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
                "last_error": warnings[0] if warnings else None,
            },
        )

        status = "partial" if failed or warnings else "success"
        return GitHubSyncResponse(
            status=status,
            repos_synced=len(request.repo_full_names),
            imported_count=imported,
            updated_count=updated,
            skipped_count=skipped,
            failed_count=failed,
            events_created=created_ids,
            warnings=warnings,
            message=f"Synced {len(request.repo_full_names)} repositories. Imported {imported}, updated {updated}, skipped {skipped}.",
            details=details,
        )

    def _require_connected(self) -> None:
        config = self._config()
        heartbeat = connector_registry_service.heartbeat_metadata("github")
        if not connector_registry_service.is_enabled("github") or not config.get("token") or not heartbeat.get("username"):
            raise GitHubConnectorError("GitHub connector is not connected.")

    def _sync_commits(self, repo: str, limit: int) -> dict[str, Any]:
        commits = self._request("GET", f"/repos/{repo}/commits", params={"per_page": limit})
        result = {"created": 0, "updated": 0, "seen": 0, "ids": []}
        for item in commits if isinstance(commits, list) else []:
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            sha = str(item.get("sha") or "")
            if not sha:
                continue
            message = str(commit.get("message") or "").strip()
            title = first_line(message) or sha[:7]
            url = str(item.get("html_url") or "")
            metadata = {
                "repo": repo,
                "sha": sha,
                "url": url,
                "author": str(author.get("name") or ""),
                "committed_at": str(author.get("date") or ""),
                "dedupe_key": f"{repo}:commit:{sha}",
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            }
            content = "\n".join(
                [
                    f"Repository: {repo}",
                    f"Commit: {message}",
                    f"Author: {metadata['author']}",
                    f"Date: {metadata['committed_at']}",
                    f"URL: {url}",
                ]
            )
            upsert = self._upsert_event("github_commit", f"GitHub commit: {title}", content, metadata, _parse_datetime(metadata["committed_at"]))
            result["created"] += int(upsert["created"])
            result["updated"] += int(not upsert["created"])
            if upsert["event_id"]:
                result["ids"].append(upsert["event_id"])
            result["seen"] += 1
        return result

    def _sync_issues(self, repo: str, limit: int) -> dict[str, Any]:
        issues = self._request("GET", f"/repos/{repo}/issues", params={"state": "open", "per_page": limit})
        result = {"created": 0, "updated": 0, "skipped": 0, "seen": 0, "ids": []}
        for item in issues if isinstance(issues, list) else []:
            if item.get("pull_request"):
                result["skipped"] += 1
                continue
            upsert = self._upsert_issue_like(repo, item, "github_issue", "GitHub issue", "Issue")
            result["created"] += int(upsert["created"])
            result["updated"] += int(not upsert["created"])
            if upsert["event_id"]:
                result["ids"].append(upsert["event_id"])
            result["seen"] += 1
        return result

    def _sync_pull_requests(self, repo: str, limit: int) -> dict[str, Any]:
        pulls = self._request("GET", f"/repos/{repo}/pulls", params={"state": "open", "per_page": limit})
        result = {"created": 0, "updated": 0, "seen": 0, "ids": []}
        for item in pulls if isinstance(pulls, list) else []:
            upsert = self._upsert_issue_like(repo, item, "github_pull_request", "GitHub PR", "PR")
            result["created"] += int(upsert["created"])
            result["updated"] += int(not upsert["created"])
            if upsert["event_id"]:
                result["ids"].append(upsert["event_id"])
            result["seen"] += 1
        return result

    def _upsert_issue_like(self, repo: str, item: dict[str, Any], event_type: str, title_prefix: str, label: str) -> dict[str, Any]:
        number = int(item.get("number") or 0)
        title = str(item.get("title") or "").strip()
        url = str(item.get("html_url") or "")
        body = str(item.get("body") or "").strip()
        labels = [str(label_item.get("name") or "") for label_item in item.get("labels") or [] if isinstance(label_item, dict)]
        head = item.get("head") or {}
        base = item.get("base") or {}
        metadata = {
            "repo": repo,
            "number": number,
            "url": url,
            "state": str(item.get("state") or "open"),
            "labels": labels,
            "source_branch": str((head.get("ref") if isinstance(head, dict) else "") or ""),
            "target_branch": str((base.get("ref") if isinstance(base, dict) else "") or ""),
            "dedupe_key": f"{repo}:{event_type}:{number}",
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
        content = "\n".join(
            [
                f"Repository: {repo}",
                f"{label} #{number}: {title}",
                f"State: {metadata['state']}",
                f"URL: {url}",
                f"Body excerpt: {body[:1200]}",
            ]
        )
        return self._upsert_event(event_type, f"{title_prefix}: #{number} {title}", content, metadata, _parse_datetime(item.get("updated_at")))

    def _upsert_event(self, event_type: str, title: str, content: str, metadata: dict[str, Any], timestamp: datetime | None) -> dict[str, Any]:
        existing = self._events.find_event_by_metadata("github", event_type, "dedupe_key", str(metadata["dedupe_key"]))
        if existing:
            merged_metadata = {**existing.metadata, **metadata}
            self._events.update_event_content_and_metadata(existing.id, content=content, metadata=merged_metadata, title=title, timestamp=timestamp)
            return {"created": False, "event_id": existing.id}
        payload: dict[str, Any] = {
            "source": EventSource.github,
            "type": event_type,
            "title": title,
            "content": content,
            "metadata": metadata,
            "embedding_status": EmbeddingStatus.not_required,
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        event = self._events.create_event(payload)
        relationship_service.detect_relationships_for_event(event)
        return {"created": True, "event_id": event.id}

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        config = self._config()
        token = str(config.get("token") or "").strip()
        if not token:
            raise GitHubConnectorError("GitHub token is not configured.")
        base_url = str(config.get("api_base_url") or DEFAULT_API_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "MindOS",
        }
        try:
            with httpx.Client(base_url=base_url, headers=headers, timeout=30.0, follow_redirects=True) as client:
                response = client.request(method, path, params=params)
        except httpx.HTTPError as error:
            connector_registry_service.record_seen("github", {"last_error": "GitHub connection failed."})
            raise GitHubConnectorError("GitHub connection failed. Check your network and token.") from error
        if response.status_code == 401:
            connector_registry_service.record_seen("github", {"last_error": "GitHub token is invalid or expired."})
            raise GitHubConnectorError("GitHub token is invalid or expired.")
        if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
            connector_registry_service.record_seen("github", {"last_error": "GitHub rate limit reached. Try again later."})
            raise GitHubConnectorError("GitHub rate limit reached. Try again later.")
        if response.status_code >= 400:
            connector_registry_service.record_seen("github", {"last_error": f"GitHub API returned {response.status_code}."})
            raise GitHubConnectorError(f"GitHub API returned {response.status_code}.")
        return response.json()

    def _config(self) -> dict[str, Any]:
        config = connector_registry_service.get_config_dict("github")
        config.setdefault("api_base_url", DEFAULT_API_BASE_URL)
        return config


def first_line(value: str) -> str:
    return value.strip().splitlines()[0] if value.strip() else ""


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _default_sync_settings() -> dict[str, Any]:
    return {
        "commits": True,
        "issues": True,
        "pull_requests": True,
        "max_items_per_type": 30,
    }


github_service = GitHubService()
