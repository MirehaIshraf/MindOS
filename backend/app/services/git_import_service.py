from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.core.dependencies import get_event_repository
from app.domain.enums import EmbeddingStatus
from app.repositories.base import EventRepository
from app.schemas.connectors import GitCommitPreview, GitImportRequest, GitImportResult, GitPreviewRequest, GitPreviewResult
from app.services.relationship_service import relationship_service

GIT_TIMEOUT_SECONDS = 10
COMMIT_SEPARATOR = "\x1f"


class GitImportService:
    def __init__(self, event_repository: EventRepository | None = None) -> None:
        self._event_repository = event_repository or get_event_repository()

    def preview_repo(self, request: GitPreviewRequest) -> GitPreviewResult:
        repo = self._validate_repo(request.repo_path)
        repo_name = repo.name
        branch = self._current_branch(repo)
        commits = self._recent_commits(repo, request.max_commits)
        status = self._status_summary(repo)
        return GitPreviewResult(
            repo_path=str(repo),
            repo_name=repo_name,
            current_branch=branch,
            is_git_repo=True,
            recent_commits=commits,
            status_summary=status["summary"],
            message=f"Found {len(commits)} recent commits in {repo_name}.",
        )

    def import_repo(self, request: GitImportRequest) -> GitImportResult:
        repo = self._validate_repo(request.repo_path)
        repo_name = repo.name
        branch = self._current_branch(repo)
        commits = self._recent_commits(repo, request.max_commits)
        status = self._status_summary(repo)
        existing_commit_hashes = self._existing_commit_hashes()
        existing_content_hashes = self._existing_content_hashes()
        imported: list[str] = []
        skipped = 0
        failed = 0

        snapshot_id = self._create_snapshot_event(
            repo=repo,
            repo_name=repo_name,
            branch=branch,
            status_summary=status["summary"],
            latest_commit=commits[0].hash if commits else "",
            existing_content_hashes=existing_content_hashes,
        )
        if snapshot_id:
            imported.append(snapshot_id)
        else:
            skipped += 1

        for commit in commits:
            if commit.hash in existing_commit_hashes:
                skipped += 1
                continue
            try:
                event_id = self._create_commit_event(repo, repo_name, commit, request.include_diff_summary)
                imported.append(event_id)
                existing_commit_hashes.add(commit.hash)
            except Exception:
                failed += 1

        if request.include_status and status["changed_files"]:
            status_id = self._create_status_event(
                repo=repo,
                repo_name=repo_name,
                branch=branch,
                status_summary=status["summary"],
                changed_files=status["changed_files"],
                existing_content_hashes=existing_content_hashes,
            )
            if status_id:
                imported.append(status_id)
            else:
                skipped += 1

        return GitImportResult(
            imported_count=len(imported),
            skipped_count=skipped,
            failed_count=failed,
            events_created=imported,
            message=f"Imported {len(imported)} Git memory events from {repo_name}.",
        )

    def _validate_repo(self, repo_path: str) -> Path:
        if shutil.which("git") is None:
            raise ValueError("Git executable was not found.")
        path = Path(repo_path).expanduser()
        if not path.exists():
            raise ValueError("Repository path does not exist.")
        if not path.is_dir():
            raise ValueError("Repository path must be a directory.")
        inside = self._git(path, ["rev-parse", "--is-inside-work-tree"]).strip()
        if inside.lower() != "true":
            raise ValueError("Path is not a Git repository.")
        top_level = self._git(path, ["rev-parse", "--show-toplevel"]).strip()
        return Path(top_level).resolve()

    def _git(self, repo: Path, args: list[str]) -> str:
        command = ["git", "-C", str(repo), *args]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as error:
            raise ValueError("Git command timed out.") from error
        except PermissionError as error:
            raise ValueError("Permission denied while reading Git repository.") from error
        except FileNotFoundError as error:
            raise ValueError("Git executable was not found.") from error
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or "Git command failed.")
        return result.stdout

    def _current_branch(self, repo: Path) -> str | None:
        branch = self._git(repo, ["branch", "--show-current"]).strip()
        return branch or None

    def _recent_commits(self, repo: Path, max_commits: int) -> list[GitCommitPreview]:
        fmt = f"%H{COMMIT_SEPARATOR}%h{COMMIT_SEPARATOR}%an{COMMIT_SEPARATOR}%ad{COMMIT_SEPARATOR}%s"
        output = self._git(repo, ["log", f"--pretty=format:{fmt}", "--date=iso-strict", "-n", str(max_commits)])
        commits: list[GitCommitPreview] = []
        for line in output.splitlines():
            parts = line.split(COMMIT_SEPARATOR)
            if len(parts) != 5:
                continue
            commits.append(GitCommitPreview(hash=parts[0], short_hash=parts[1], author=parts[2], date=parts[3], message=parts[4]))
        return commits

    def _status_summary(self, repo: Path) -> dict:
        output = self._git(repo, ["status", "--short"])
        summary = {"modified": 0, "added": 0, "deleted": 0, "untracked": 0}
        changed_files: list[dict[str, str]] = []
        for line in output.splitlines():
            if not line:
                continue
            code = line[:2]
            path = line[3:].strip()
            category = self._status_category(code)
            summary[category] += 1
            changed_files.append({"status": category, "code": code.strip(), "path": path})
        return {"summary": summary, "changed_files": changed_files}

    def _status_category(self, code: str) -> str:
        if code == "??":
            return "untracked"
        if "D" in code:
            return "deleted"
        if "A" in code:
            return "added"
        return "modified"

    def _create_snapshot_event(
        self,
        *,
        repo: Path,
        repo_name: str,
        branch: str | None,
        status_summary: dict,
        latest_commit: str,
        existing_content_hashes: set[str],
    ) -> str | None:
        content = (
            f"Repository {repo_name} on branch {branch or 'detached HEAD'}. "
            f"Working tree has {status_summary['modified']} modified, {status_summary['added']} added, "
            f"{status_summary['deleted']} deleted, {status_summary['untracked']} untracked files."
        )
        content_hash = self._hash({"repo": str(repo), "branch": branch, "status": status_summary, "latest": latest_commit})
        if content_hash in existing_content_hashes:
            return None
        event = self._event_repository.create_event(
            {
                "source": "git",
                "type": "git_repo_snapshot",
                "title": f"Git repository snapshot: {repo_name}",
                "content": content,
                "metadata": {
                    "repo_path": str(repo),
                    "repo_name": repo_name,
                    "current_branch": branch,
                    "status_summary": status_summary,
                    "latest_commit": latest_commit,
                    "content_hash": content_hash,
                    "import_method": "manual_git_import",
                },
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        existing_content_hashes.add(content_hash)
        relationship_service.detect_relationships_for_event(event)
        return event.id

    def _create_commit_event(self, repo: Path, repo_name: str, commit: GitCommitPreview, include_diff_summary: bool) -> str:
        diff_summary = ""
        if include_diff_summary:
            diff_summary = self._git(repo, ["show", "--stat", "--oneline", "--no-renames", commit.hash]).strip()
        content = (
            f"Commit hash: {commit.hash}\n"
            f"Author: {commit.author}\n"
            f"Date: {commit.date}\n"
            f"Message: {commit.message}"
        )
        if diff_summary:
            content += f"\n\nDiff summary:\n{diff_summary}"
        event = self._event_repository.create_event(
            {
                "source": "git",
                "type": "git_commit",
                "title": f"{commit.short_hash}: {commit.message}",
                "content": content,
                "metadata": {
                    "repo_path": str(repo),
                    "repo_name": repo_name,
                    "commit_hash": commit.hash,
                    "short_hash": commit.short_hash,
                    "author": commit.author,
                    "date": commit.date,
                    "import_method": "manual_git_import",
                },
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        relationship_service.detect_relationships_for_event(event)
        return event.id

    def _create_status_event(
        self,
        *,
        repo: Path,
        repo_name: str,
        branch: str | None,
        status_summary: dict,
        changed_files: list[dict[str, str]],
        existing_content_hashes: set[str],
    ) -> str | None:
        content_hash = self._hash({"repo": str(repo), "branch": branch, "status": status_summary, "files": changed_files})
        if content_hash in existing_content_hashes:
            return None
        grouped = {key: [item["path"] for item in changed_files if item["status"] == key] for key in ["modified", "added", "deleted", "untracked"]}
        content = "\n".join(
            [f"{label.title()}:\n" + "\n".join(f"- {path}" for path in paths) for label, paths in grouped.items() if paths]
        )
        event = self._event_repository.create_event(
            {
                "source": "git",
                "type": "git_working_tree_status",
                "title": f"Uncommitted changes in {repo_name}",
                "content": content,
                "metadata": {
                    "repo_path": str(repo),
                    "repo_name": repo_name,
                    "current_branch": branch,
                    "status_summary": status_summary,
                    "changed_files": changed_files,
                    "content_hash": content_hash,
                    "import_method": "manual_git_import",
                },
                "timestamp": datetime.now(timezone.utc),
                "embedding_status": EmbeddingStatus.not_required,
            }
        )
        existing_content_hashes.add(content_hash)
        relationship_service.detect_relationships_for_event(event)
        return event.id

    def _existing_commit_hashes(self) -> set[str]:
        hashes: set[str] = set()
        for event in self._event_repository.list_all_events(include_hidden=True):
            if event.source.value == "git" and event.type == "git_commit":
                value = event.metadata.get("commit_hash")
                if isinstance(value, str):
                    hashes.add(value)
        return hashes

    def _existing_content_hashes(self) -> set[str]:
        hashes: set[str] = set()
        for event in self._event_repository.list_all_events(include_hidden=True):
            if event.source.value == "git":
                value = event.metadata.get("content_hash")
                if isinstance(value, str):
                    hashes.add(value)
        return hashes

    def _hash(self, value: object) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
