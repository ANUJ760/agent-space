"""Project file workspaces and Git checkpoints on a shared persistent volume."""

import fcntl
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app.config import get_settings
from app.errors import BadRequestError, ConflictError, NotFoundError

MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 500


def workspace_dir(project_id: uuid.UUID) -> Path:
    root = Path(get_settings().workspace_root).expanduser().resolve()
    return root / str(project_id)


def file_path(project_id: uuid.UUID, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        not relative
        or path.is_absolute()
        or any(part in ("", ".", "..") or part.startswith(".") for part in relative.split("/"))
        or "\\" in relative
        or "\x00" in relative
    ):
        raise BadRequestError("Invalid workspace file path.")
    root = workspace_dir(project_id)
    candidate = root.joinpath(*path.parts)
    if not candidate.resolve().is_relative_to(root):
        raise BadRequestError("Invalid workspace file path.")
    return candidate


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=45,
        env=env,
        check=False,
    )
    if process.returncode:
        raise BadRequestError(process.stderr.strip()[:300] or "Git operation failed.")
    return process.stdout.strip()


@contextmanager
def _git_lock(root: Path):
    with (root / ".git" / "agentspace.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
        fcntl.flock(handle, fcntl.LOCK_UN)


def create_workspace(project_id: uuid.UUID, branch: str = "main") -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,98}", branch) or ".." in branch:
        raise BadRequestError("Invalid default branch.")
    root = workspace_dir(project_id)
    if (root / ".git").exists():
        return
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", branch)
    (root / "README.md").write_text("# Project workspace\n\nEdit files together in Agent Space.\n")
    (root / ".gitignore").write_text(".yjs/\n.env\n.env.*\n*.key\n*.pem\n")
    _git(root, "add", "--", "README.md", ".gitignore")
    _git(root, "-c", "user.name=Agent Space", "-c", "user.email=workspace@agentspace.local", "commit", "-m", "Initialize project workspace")


def list_files(project_id: uuid.UUID) -> list[dict[str, str | int]]:
    root = workspace_dir(project_id)
    if not root.exists():
        return []
    files = []
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not name.startswith(".") and not (Path(current) / name).is_symlink()]
        for name in names:
            if name.startswith("."):
                continue
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            files.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size})
            if len(files) >= MAX_FILES:
                return sorted(files, key=lambda item: str(item["path"]))
    return sorted(files, key=lambda item: str(item["path"]))


def read_file(project_id: uuid.UUID, relative: str) -> str:
    path = file_path(project_id, relative)
    if not path.is_file():
        raise NotFoundError("Workspace file", relative)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise BadRequestError("File exceeds the 1 MB editor limit.")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError("Only UTF-8 text files are supported.") from exc


def write_file(project_id: uuid.UUID, relative: str, content: str, *, create_only: bool = False) -> None:
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise BadRequestError("File exceeds the 1 MB editor limit.")
    path = file_path(project_id, relative)
    root = workspace_dir(project_id)
    if not root.exists():
        raise NotFoundError("Workspace", str(project_id))
    if create_only and path.exists():
        raise ConflictError("FILE_EXISTS", "File already exists.")
    if create_only and len(list_files(project_id)) >= MAX_FILES:
        raise BadRequestError("Workspace file limit reached.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    os.replace(temporary, path)


def remove_workspace(project_id: uuid.UUID) -> None:
    root = workspace_dir(project_id)
    if root.exists():
        shutil.rmtree(root)


def checkpoint(project_id: uuid.UUID, message: str, author: str) -> dict[str, str | bool]:
    root = workspace_dir(project_id)
    if not (root / ".git").exists():
        raise NotFoundError("Workspace", str(project_id))
    with _git_lock(root):
        _git(root, "add", "-A")
        if not _git(root, "status", "--porcelain"):
            return {"created": False, "commit": _git(root, "rev-parse", "HEAD")}
        _git(root, "-c", f"user.name={author[:80]}", "-c", "user.email=workspace@agentspace.local", "commit", "-m", message[:200])
        return {"created": True, "commit": _git(root, "rev-parse", "HEAD")}


def history(project_id: uuid.UUID) -> list[dict[str, str]]:
    root = workspace_dir(project_id)
    if not (root / ".git").exists():
        return []
    output = _git(root, "log", "-20", "--format=%H%x1f%s%x1f%aI")
    return [dict(zip(("commit", "message", "date"), line.split("\x1f", 2), strict=True)) for line in output.splitlines()]


def push(project_id: uuid.UUID, remote_url: str, branch: str, token: str, username: str = "x-access-token") -> str:
    parsed = urlsplit(remote_url)
    allowed = {host.strip().lower() for host in get_settings().git_allowed_hosts.split(",")}
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password:
        raise BadRequestError("Repository must use HTTPS on an allowed Git host, without embedded credentials.")
    root = workspace_dir(project_id)
    if not (root / ".git").exists():
        raise NotFoundError("Workspace", str(project_id))
    # Askpass keeps the token out of the URL, command line and persisted Git config.
    with _git_lock(root), tempfile.TemporaryDirectory() as temp_dir:
        askpass = Path(temp_dir) / "askpass.sh"
        askpass.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s" "$AGENTSPACE_GIT_USERNAME";; *) printf "%s" "$AGENTSPACE_GIT_TOKEN";; esac\n')
        askpass.chmod(0o700)
        env = {**os.environ, "GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0", "AGENTSPACE_GIT_TOKEN": token, "AGENTSPACE_GIT_USERNAME": username}
        _git(root, "-c", "http.followRedirects=false", "push", remote_url, f"HEAD:refs/heads/{branch}", env=env)
    return _git(root, "rev-parse", "HEAD")


def auto_checkpoint_all() -> None:
    root = Path(get_settings().workspace_root).expanduser().resolve()
    if not root.exists():
        return
    for directory in root.iterdir():
        if not directory.is_dir() or not (directory / ".git").is_dir():
            continue
        try:
            checkpoint(uuid.UUID(directory.name), "Automatic workspace checkpoint", "Agent Space")
        except (ValueError, BadRequestError, NotFoundError, FileNotFoundError):
            continue
