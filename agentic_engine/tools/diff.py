"""Git diff tools — show repo state to agents and to the CLI."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..core.tool import tool


def _is_git_repo(repo: str) -> bool:
    r = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and r.stdout.strip() == "true"


def _git_text(repo: str, *args: str) -> str:
    if shutil.which("git") is None:
        return "[error] git executable not found in PATH"
    p = Path(repo)
    if not p.exists():
        return f"[error] path does not exist: {repo}"
    if not _is_git_repo(repo):
        return f"[error] not a git repository: {repo} (run `git init` here, or pass a path that is)"
    r = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True, text=True,
    )
    return r.stdout if r.returncode == 0 else f"[git error] {r.stderr.strip()}"


@tool(name="git_status", description="Show `git status --porcelain` for a repo.", read_only=True)
def git_status(repo: str = ".") -> str:
    return _git_text(str(Path(repo).resolve()), "status", "--porcelain")


@tool(name="git_diff", description="Show unified diff. Optional file path.", read_only=True)
def git_diff(repo: str = ".", path: str = "", staged: bool = False, max_chars: int = 8000) -> str:
    args = ["diff", "--unified=3"]
    if staged:
        args.append("--cached")
    if path:
        args.extend(["--", path])
    out = _git_text(str(Path(repo).resolve()), *args)
    return out[:max_chars]


@tool(name="git_log", description="Show recent commit log.", read_only=True)
def git_log(repo: str = ".", n: int = 20) -> str:
    return _git_text(str(Path(repo).resolve()), "log", f"-n{n}", "--oneline", "--decorate")
