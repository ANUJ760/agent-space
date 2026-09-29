"""Unit tests for Gitea integration client."""

import httpx
import pytest

from packages.gitea.client import (
    CommitFileInfo,
    GiteaClient,
    GiteaConflictError,
    GiteaNotFoundError,
)


@pytest.fixture
def mock_gitea_transport():
    """Mock HTTP transport simulating Gitea v1 API endpoints."""
    repos = {}
    branches = {"testorg/testrepo": ["main"]}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method

        # Auth check
        auth = request.headers.get("Authorization")
        if not auth or "token" not in auth:
            return httpx.Response(401, json={"message": "Unauthorized"})

        # Repo creation: POST /api/v1/orgs/{org}/repos
        if method == "POST" and "/api/v1/orgs/" in url and url.endswith("/repos"):
            import json
            data = json.loads(request.content.decode("utf-8"))
            repo_name = data["name"]
            org = url.split("/orgs/")[1].split("/repos")[0]
            key = f"{org}/{repo_name}"
            if key in repos:
                return httpx.Response(409, json={"message": "Repo already exists"})
            repo_data = {
                "id": len(repos) + 1,
                "name": repo_name,
                "full_name": key,
                "default_branch": data.get("default_branch", "main"),
                "clone_url": f"http://localhost:3001/{key}.git",
            }
            repos[key] = repo_data
            branches[key] = [data.get("default_branch", "main")]
            return httpx.Response(201, json=repo_data)

        # Get repo: GET /api/v1/repos/{owner}/{repo}
        if method == "GET" and "/api/v1/repos/" in url and "/branches" not in url and "/compare" not in url:
            parts = url.split("/api/v1/repos/")[1].split("/")
            key = f"{parts[0]}/{parts[1]}"
            if key not in repos:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json=repos[key])

        # Create branch: POST /api/v1/repos/{owner}/{repo}/branches
        if method == "POST" and "/branches" in url:
            import json
            parts = url.split("/api/v1/repos/")[1].split("/branches")[0].split("/")
            key = f"{parts[0]}/{parts[1]}"
            data = json.loads(request.content.decode("utf-8"))
            new_branch = data["new_branch_name"]
            if new_branch in branches.get(key, []):
                return httpx.Response(409, json={"message": "Branch already exists"})
            branches.setdefault(key, []).append(new_branch)
            return httpx.Response(201, json={"name": new_branch})

        # List branches: GET /api/v1/repos/{owner}/{repo}/branches
        if method == "GET" and "/branches" in url and not url.endswith(("/branches/main", "/branches/feature")):
            parts = url.split("/api/v1/repos/")[1].split("/branches")[0].split("/")
            key = f"{parts[0]}/{parts[1]}"
            b_list = [{"name": b} for b in branches.get(key, [])]
            return httpx.Response(200, json=b_list)

        # Commit files: POST /api/v1/repos/{owner}/{repo}/contents
        if method == "POST" and "/contents" in url:
            import json
            data = json.loads(request.content.decode("utf-8"))
            return httpx.Response(201, json={"commit": {"sha": "c0ffee123", "message": data["message"]}})

        # Diff: GET /api/v1/repos/{owner}/{repo}/compare/{base}...{head}.diff
        if method == "GET" and "/compare/" in url:
            diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,2 @@\n+print('hello')\n"
            return httpx.Response(200, text=diff_text)

        # Scoped Token: POST /api/v1/users/{username}/tokens
        if method == "POST" and "/tokens" in url:
            import json
            data = json.loads(request.content.decode("utf-8"))
            return httpx.Response(201, json={"name": data["name"], "sha1": "scoped_token_abc123", "scopes": data["scopes"]})

        return httpx.Response(404, json={"message": "Not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_gitea_repository_and_branch_lifecycle(mock_gitea_transport):
    async with httpx.AsyncClient(transport=mock_gitea_transport) as client:
        gitea = GiteaClient(admin_token="admin-secret-token", http_client=client)

        # 1. Create Repo
        repo = await gitea.create_repository(owner="testorg", repo_name="demo-repo")
        assert repo["name"] == "demo-repo"

        # 2. Get Repo
        fetched = await gitea.get_repository(owner="testorg", repo_name="demo-repo")
        assert fetched["full_name"] == "testorg/demo-repo"

        # 3. Create Branch
        branch = await gitea.create_branch(owner="testorg", repo_name="demo-repo", branch_name="agent/task-101")
        assert branch["name"] == "agent/task-101"

        # 4. List Branches
        all_branches = await gitea.list_branches(owner="testorg", repo_name="demo-repo")
        branch_names = [b["name"] for b in all_branches]
        assert "main" in branch_names
        assert "agent/task-101" in branch_names


@pytest.mark.asyncio
async def test_gitea_commit_and_diff(mock_gitea_transport):
    async with httpx.AsyncClient(transport=mock_gitea_transport) as client:
        gitea = GiteaClient(admin_token="admin-secret-token", http_client=client)

        files = [
            CommitFileInfo(path="src/main.py", content="print('hello')\n"),
        ]
        commit_res = await gitea.create_commit(
            owner="testorg",
            repo_name="demo-repo",
            branch="agent/task-101",
            files=files,
            message="feat: add hello world",
        )
        assert commit_res["commit"]["sha"] == "c0ffee123"

        diff = await gitea.get_diff(owner="testorg", repo_name="demo-repo", base="main", head="agent/task-101")
        assert "+print('hello')" in diff


@pytest.mark.asyncio
async def test_gitea_scoped_token_isolation(mock_gitea_transport):
    async with httpx.AsyncClient(transport=mock_gitea_transport) as client:
        admin_token = "admin-secret-token"
        gitea = GiteaClient(admin_token=admin_token, http_client=client)

        scoped_cred = await gitea.generate_scoped_token(
            username="testagent",
            repo_owner="testorg",
            repo_name="demo-repo",
            scopes=["repo:read", "repo:write"],
        )
        # Agent gets scoped token, NOT the admin token
        assert scoped_cred.token == "scoped_token_abc123"
        assert scoped_cred.token != admin_token
        assert scoped_cred.repository == "testorg/demo-repo"
        assert "repo:write" in scoped_cred.scopes


@pytest.mark.asyncio
async def test_gitea_error_handling(mock_gitea_transport):
    async with httpx.AsyncClient(transport=mock_gitea_transport) as client:
        gitea = GiteaClient(admin_token="admin-secret-token", http_client=client)

        # 404
        with pytest.raises(GiteaNotFoundError):
            await gitea.get_repository(owner="unknown", repo_name="nonexistent")

        # Conflict
        await gitea.create_repository(owner="testorg", repo_name="unique-repo")
        with pytest.raises(GiteaConflictError):
            await gitea.create_repository(owner="testorg", repo_name="unique-repo")
