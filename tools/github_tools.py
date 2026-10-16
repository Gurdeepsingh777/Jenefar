from __future__ import annotations

import base64
import posixpath
from typing import Any
from urllib.parse import quote

import httpx

from agent.tool_registry import ToolRegistry
from config import Settings


class GitHubToolError(RuntimeError):
    """An actionable GitHub REST API failure."""


def register_github_tools(registry: ToolRegistry, settings: Settings) -> None:
    async def github_request(
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> Any:
        if not settings.github_pat:
            raise GitHubToolError(
                "GitHub tools are disabled because GITHUB_PAT is not configured."
            )
        url = settings.github_api_url.rstrip("/") + path
        headers = {
            "Authorization": f"Bearer {settings.github_pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Jenefar-Telegram-Agent",
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.request_timeout_seconds),
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise GitHubToolError("GitHub API request timed out. Try again shortly.") from exc
        except httpx.RequestError as exc:
            raise GitHubToolError(
                f"Could not connect to GitHub ({type(exc).__name__})."
            ) from exc

        if response.status_code == 404 and allow_not_found:
            return None
        if response.status_code == 401:
            raise GitHubToolError("GitHub rejected GITHUB_PAT. Check that the token is valid.")
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                raise GitHubToolError(
                    "GitHub API rate limit reached. Wait for the reset window and retry."
                )
            raise GitHubToolError(
                "GitHub denied this request. Check repository access and PAT permissions."
            )
        if response.status_code == 429:
            raise GitHubToolError("GitHub rate-limited the request. Retry later.")
        if not response.is_success:
            message = ""
            try:
                body = response.json()
                message = str(body.get("message") or "")
            except (ValueError, AttributeError):
                pass
            message = message.replace("\n", " ").strip()[:500]
            suffix = f": {message}" if message else ""
            raise GitHubToolError(
                f"GitHub API returned HTTP {response.status_code}{suffix}"
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubToolError("GitHub returned invalid JSON.") from exc

    def validate_owner_repo(arguments: dict[str, Any]) -> tuple[str, str]:
        owner = str(arguments.get("owner") or "").strip()
        repo = str(arguments.get("repo") or "").strip()
        if "/" in owner or "/" in repo or not owner or not repo:
            combined = str(arguments.get("repository") or "").strip().split("/", 1)
            if len(combined) == 2 and all(combined):
                owner, repo = combined[0].strip(), combined[1].strip()
        if not owner or not repo or "/" in owner or "/" in repo or any(x in owner + repo for x in (" ", "\n", "\r")):
            raise ValueError("Provide owner and repo separately, or repository as owner/repo.")
        return owner, repo

    def validate_file_path(raw: Any) -> str:
        path = str(raw or "").strip().replace("\\", "/")
        if not path or path.startswith("/"):
            raise ValueError("File path must be a non-empty relative repository path.")
        if any(part in {".", "..", ""} for part in path.split("/")):
            raise ValueError("File path cannot contain empty, '.' or '..' path segments.")
        if "\x00" in path:
            raise ValueError("File path contains an invalid character.")
        normalized = posixpath.normpath(path)
        if normalized in {"", ".", ".."} or normalized.startswith("../"):
            raise ValueError("Invalid repository file path.")
        return normalized

    @registry.tool(
        name="list_repos",
        description="List repositories owned by the authenticated GitHub user. Read-only.",
        parameters={
            "type": "object",
            "properties": {
                "visibility": {"type": "string", "enum": ["all", "public", "private"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": [],
            "additionalProperties": False,
        },
    )
    async def list_repos(arguments: dict[str, Any]) -> dict[str, Any]:
        visibility = str(arguments.get("visibility") or "all").lower()
        if visibility not in {"all", "public", "private"}:
            raise ValueError("visibility must be all, public, or private.")
        limit = max(1, min(100, int(arguments.get("limit", 50))))
        repos: list[dict[str, Any]] = []
        page = 1
        while len(repos) < limit:
            page_items = await github_request(
                "GET",
                "/user/repos",
                params={
                    "visibility": visibility,
                    "sort": "updated",
                    "per_page": min(100, limit - len(repos)),
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            if not isinstance(page_items, list) or not page_items:
                break
            for item in page_items:
                repos.append({
                    "full_name": item.get("full_name"),
                    "private": item.get("private"),
                    "default_branch": item.get("default_branch"),
                    "description": item.get("description"),
                    "html_url": item.get("html_url"),
                    "updated_at": item.get("updated_at"),
                })
            page += 1
        return {"count": min(len(repos), limit), "repositories": repos[:limit]}

    @registry.tool(
        name="read_file",
        description="Read a text file from a GitHub repository branch. Read-only; returns a bounded preview.",
        parameters={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "repository": {"type": "string"},
                "path": {"type": "string"},
                "branch": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    async def read_file(arguments: dict[str, Any]) -> dict[str, Any]:
        owner, repo = validate_owner_repo(arguments)
        path = validate_file_path(arguments.get("path"))
        branch = str(arguments.get("branch") or "").strip()
        params = {"ref": branch} if branch else None
        result = await github_request(
            "GET",
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents/{quote(path, safe='/')}",
            params=params,
        )
        if not isinstance(result, dict) or result.get("type") != "file":
            raise GitHubToolError("The requested path is not a single file.")
        encoded = str(result.get("content") or "").replace("\n", "").strip()
        if result.get("encoding") == "base64":
            try:
                raw_content = base64.b64decode(encoded).decode("utf-8", errors="replace")
            except (ValueError, UnicodeError) as exc:
                raise GitHubToolError("Could not decode the file returned by GitHub.") from exc
        else:
            raise GitHubToolError(
                "GitHub did not return inline text (the file may be too large or binary)."
            )
        max_chars = min(9000, settings.max_tool_output_chars - 1000)
        return {
            "repository": f"{owner}/{repo}",
            "path": path,
            "branch": branch or "default branch",
            "sha": result.get("sha"),
            "size": result.get("size"),
            "content": raw_content[:max_chars],
            "truncated": len(raw_content) > max_chars,
            "html_url": result.get("html_url"),
        }

    @registry.tool(
        name="create_or_update_file",
        description=(
            "Create or update a UTF-8 text file in a GitHub repository and commit it. "
            "Only use when the current Telegram request clearly asks for the write."
        ),
        parameters={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "repository": {"type": "string"},
                "path": {"type": "string"},
                "content": {"type": "string"},
                "message": {"type": "string"},
                "branch": {"type": "string"},
            },
            "required": ["path", "content", "message"],
            "additionalProperties": False,
        },
    )
    async def create_or_update_file(arguments: dict[str, Any]) -> dict[str, Any]:
        owner, repo = validate_owner_repo(arguments)
        path = validate_file_path(arguments.get("path"))
        content = str(arguments.get("content") or "")
        message = str(arguments.get("message") or "").strip()
        branch = str(arguments.get("branch") or "").strip()
        if not message:
            raise ValueError("A non-empty commit message is required.")
        if len(content.encode("utf-8")) > 100_000:
            raise ValueError("File contents exceed the 100 KB per-call limit.")
        if len(message) > 200:
            raise ValueError("Commit message must be 200 characters or fewer.")

        endpoint = (
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents/{quote(path, safe='/')}"
        )
        params = {"ref": branch} if branch else None
        existing = await github_request(
            "GET", endpoint, params=params, allow_not_found=True
        )
        if existing is not None and (
            not isinstance(existing, dict) or existing.get("type") != "file"
        ):
            raise GitHubToolError("The target path exists but is not a file.")
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if branch:
            payload["branch"] = branch
        if existing is not None:
            payload["sha"] = existing.get("sha")

        result = await github_request("PUT", endpoint, payload=payload)
        file_info = result.get("content") or {}
        commit_info = result.get("commit") or {}
        return {
            "action": "updated" if existing is not None else "created",
            "repository": f"{owner}/{repo}",
            "path": path,
            "branch": branch or "repository default branch",
            "commit_sha": commit_info.get("sha"),
            "commit_url": commit_info.get("html_url"),
            "file_sha": file_info.get("sha"),
            "html_url": file_info.get("html_url"),
        }

    @registry.tool(
        name="create_repo",
        description="Create a repository for the authenticated GitHub user. Private by default.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "private": {"type": "boolean"},
                "auto_init": {"type": "boolean"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    )
    async def create_repo(arguments: dict[str, Any]) -> dict[str, Any]:
        name = str(arguments.get("name") or "").strip()
        if not name or len(name) > 100 or any(char in name for char in ("/", "\\", "\n", "\r")):
            raise ValueError("Provide a valid repository name without slashes or newlines.")
        result = await github_request(
            "POST",
            "/user/repos",
            payload={
                "name": name,
                "description": str(arguments.get("description") or "")[:350],
                "private": bool(arguments.get("private", True)),
                "auto_init": bool(arguments.get("auto_init", True)),
            },
        )
        return {
            "full_name": result.get("full_name"),
            "private": result.get("private"),
            "default_branch": result.get("default_branch"),
            "html_url": result.get("html_url"),
            "clone_url": result.get("clone_url"),
        }

    @registry.tool(
        name="manage_issues",
        description=(
            "List or create GitHub issues, or list/create pull requests. Use operation "
            "list_issues, create_issue, list_prs, or create_pr. Writes must be requested by the user."
        ),
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["list_issues", "create_issue", "list_prs", "create_pr"]},
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "repository": {"type": "string"},
                "state": {"type": "string", "enum": ["open", "closed", "all"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                "head": {"type": "string"},
                "base": {"type": "string"},
                "draft": {"type": "boolean"},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    )
    async def manage_issues(arguments: dict[str, Any]) -> dict[str, Any]:
        owner, repo = validate_owner_repo(arguments)
        operation = str(arguments.get("operation") or "").lower()
        state = str(arguments.get("state") or "open").lower()
        if state not in {"open", "closed", "all"}:
            raise ValueError("state must be open, closed, or all.")
        limit = max(1, min(100, int(arguments.get("limit", 20))))
        repo_path = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

        if operation == "list_issues":
            data = await github_request(
                "GET",
                repo_path + "/issues",
                params={"state": state, "per_page": limit, "page": 1},
            )
            # GitHub's issues endpoint also returns PRs; exclude them here.
            items = [item for item in (data or []) if not item.get("pull_request")]
            return {"operation": operation, "count": len(items), "items": [
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "html_url": item.get("html_url"),
                    "labels": [label.get("name") for label in item.get("labels", [])],
                }
                for item in items[:limit]
            ]}

        if operation == "create_issue":
            title = str(arguments.get("title") or "").strip()
            if not title:
                raise ValueError("A non-empty issue title is required.")
            body = str(arguments.get("body") or "")
            if len(body) > 50000:
                raise ValueError("Issue body exceeds the 50 KB limit.")
            result = await github_request(
                "POST",
                repo_path + "/issues",
                payload={
                    "title": title[:256],
                    "body": body,
                    "labels": [str(item) for item in (arguments.get("labels") or [])][:20],
                },
            )
            return {
                "operation": operation,
                "number": result.get("number"),
                "title": result.get("title"),
                "html_url": result.get("html_url"),
                "state": result.get("state"),
            }

        if operation == "list_prs":
            data = await github_request(
                "GET",
                repo_path + "/pulls",
                params={"state": state, "per_page": limit, "page": 1, "sort": "updated", "direction": "desc"},
            )
            items = data if isinstance(data, list) else []
            return {"operation": operation, "count": len(items), "items": [
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "draft": item.get("draft"),
                    "html_url": item.get("html_url"),
                    "head": (item.get("head") or {}).get("ref"),
                    "base": (item.get("base") or {}).get("ref"),
                }
                for item in items[:limit]
            ]}

        if operation == "create_pr":
            title = str(arguments.get("title") or "").strip()
            head = str(arguments.get("head") or "").strip()
            base = str(arguments.get("base") or "main").strip()
            if not title or not head or not base:
                raise ValueError("create_pr requires title, head branch, and base branch.")
            result = await github_request(
                "POST",
                repo_path + "/pulls",
                payload={
                    "title": title[:256],
                    "body": str(arguments.get("body") or "")[:50000],
                    "head": head,
                    "base": base,
                    "draft": bool(arguments.get("draft", False)),
                },
            )
            return {
                "operation": operation,
                "number": result.get("number"),
                "title": result.get("title"),
                "state": result.get("state"),
                "html_url": result.get("html_url"),
                "draft": result.get("draft"),
            }

        raise ValueError("operation must be list_issues, create_issue, list_prs, or create_pr.")
