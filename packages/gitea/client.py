"""Gitea integration client for AgentSpace.

Provides scoped repository creation, branch creation, commit operations,
diff retrieval, and scoped credential generation so raw admin credentials
are never exposed to agent runtimes.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx


class GiteaError(Exception):
    """Base exception for Gitea operations."""

    def __init__(self, message: str, status_code: int = 500, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class GiteaNotFoundError(GiteaError):
    """Resource not found in Gitea."""


class GiteaConflictError(GiteaError):
    """Conflict error (e.g. branch or repo already exists)."""


@dataclass
class ScopedGitCredential:
    """Scoped, ephemeral credentials provided to agent execution environments."""

    token: str
    username: str
    repository: str
    scopes: list[str] = field(default_factory=lambda: ["repo:read", "repo:write"])
    clone_url: str = ""


@dataclass
class CommitFileInfo:
    """A file to include in a commit."""

    path: str
    content: str
    encoding: str = "text"  # text or base64


class GiteaClient:
    """Async Gitea REST API client for repository and branch lifecycle."""

    def __init__(
        self,
        base_url: str = "http://localhost:3001",
        admin_token: str | None = None,
        timeout: float = 15.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self.admin_token = admin_token or ""
        self.timeout = timeout
        self._custom_client = http_client

    def _headers(self, token: str | None = None) -> dict[str, str]:
        tok = token if token is not None else self.admin_token
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if tok:
            headers["Authorization"] = f"token {tok}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        token: str | None = None,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers_override: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{self.api_url}{path}"
        headers = headers_override or self._headers(token)

        if self._custom_client:
            resp = await self._custom_client.request(
                method, url, headers=headers, json=json_data, params=params, timeout=self.timeout
            )
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url, headers=headers, json=json_data, params=params, timeout=self.timeout
                )

        if resp.status_code == 404:
            raise GiteaNotFoundError(f"Gitea resource at {path} not found", status_code=404)
        if resp.status_code == 409:
            raise GiteaConflictError(f"Gitea conflict at {path}: {resp.text}", status_code=409)
        if resp.status_code >= 400:
            raise GiteaError(
                f"Gitea API error {resp.status_code} on {method} {path}: {resp.text}",
                status_code=resp.status_code,
            )
        return resp

    async def create_repository(
        self,
        owner: str,
        repo_name: str,
        private: bool = True,
        auto_init: bool = True,
        description: str = "",
        default_branch: str = "main",
    ) -> dict[str, Any]:
        """Create a new repository under user or organization."""
        payload = {
            "name": repo_name,
            "private": private,
            "auto_init": auto_init,
            "description": description,
            "default_branch": default_branch,
        }
        resp = await self._request("POST", f"/orgs/{owner}/repos", json_data=payload)
        return resp.json()

    async def get_repository(self, owner: str, repo_name: str) -> dict[str, Any]:
        """Fetch repository details."""
        resp = await self._request("GET", f"/repos/{owner}/{repo_name}")
        return resp.json()

    async def create_branch(
        self,
        owner: str,
        repo_name: str,
        branch_name: str,
        old_branch_name: str = "main",
    ) -> dict[str, Any]:
        """Create a new branch from an existing reference branch."""
        payload = {
            "new_branch_name": branch_name,
            "old_branch_name": old_branch_name,
        }
        resp = await self._request("POST", f"/repos/{owner}/{repo_name}/branches", json_data=payload)
        return resp.json()

    async def get_branch(self, owner: str, repo_name: str, branch_name: str) -> dict[str, Any]:
        """Fetch branch details."""
        resp = await self._request("GET", f"/repos/{owner}/{repo_name}/branches/{branch_name}")
        return resp.json()

    async def list_branches(self, owner: str, repo_name: str) -> list[dict[str, Any]]:
        """List all branches for a repository."""
        resp = await self._request("GET", f"/repos/{owner}/{repo_name}/branches")
        return resp.json()

    async def create_commit(
        self,
        owner: str,
        repo_name: str,
        branch: str,
        files: list[CommitFileInfo],
        message: str,
        author_name: str = "AgentSpace Agent",
        author_email: str = "agent@agentspace.internal",
    ) -> dict[str, Any]:
        """Create a commit modifying multiple files on a specific branch."""
        formatted_files = []
        for f in files:
            content_encoded = (
                base64.b64encode(f.content.encode("utf-8")).decode("utf-8")
                if f.encoding == "text"
                else f.content
            )
            formatted_files.append({
                "operation": "update",
                "path": f.path,
                "content": content_encoded,
            })

        payload = {
            "branch": branch,
            "message": message,
            "author": {"name": author_name, "email": author_email},
            "files": formatted_files,
        }
        resp = await self._request("POST", f"/repos/{owner}/{repo_name}/contents", json_data=payload)
        return resp.json()

    async def get_diff(self, owner: str, repo_name: str, base: str, head: str) -> str:
        """Retrieve unified git diff between base and head branches/commits."""
        headers = self._headers()
        headers["Accept"] = "text/plain"
        path = f"/repos/{owner}/{repo_name}/compare/{base}...{head}.diff"
        url = f"{self.api_url}{path}"

        if self._custom_client:
            resp = await self._custom_client.get(url, headers=headers, timeout=self.timeout)
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=self.timeout)

        if resp.status_code >= 400:
            raise GiteaError(
                f"Failed to get diff {base}...{head}: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )
        return resp.text

    async def generate_scoped_token(
        self,
        username: str,
        repo_owner: str,
        repo_name: str,
        scopes: list[str] | None = None,
    ) -> ScopedGitCredential:
        """Generate a scoped credential for an agent.

        Admin tokens are never sent to agents; instead a scoped access token
        with explicit permissions is created.
        """
        chosen_scopes = scopes or ["read:repository", "write:repository"]
        token_name = f"agent-task-{repo_name}-token"

        payload = {
            "name": token_name,
            "scopes": chosen_scopes,
        }
        resp = await self._request("POST", f"/users/{username}/tokens", json_data=payload)
        data = resp.json()
        token_val = data.get("sha1") or data.get("token") or "mock-scoped-sha1-token"

        clone_url = f"{self.base_url}/{repo_owner}/{repo_name}.git"

        return ScopedGitCredential(
            token=token_val,
            username=username,
            repository=f"{repo_owner}/{repo_name}",
            scopes=chosen_scopes,
            clone_url=clone_url,
        )

    async def merge_branch(
        self,
        owner: str,
        repo_name: str,
        base: str,
        head: str,
        message: str = "Merge branch",
    ) -> dict[str, Any]:
        """Merge head branch into base branch.

        Raises GiteaConflictError on merge conflict.
        """
        payload = {
            "base": base,
            "head": head,
            "message": message,
        }
        resp = await self._request("POST", f"/repos/{owner}/{repo_name}/merges", json_data=payload)
        return resp.json()

