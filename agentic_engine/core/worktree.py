"""Worktree — thin wrapper around `git worktree` for safe parallel agent runs."""
from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorktreeHandle:
    path: Path
    branch: str
    base_repo: Path

    def remove(self, force: bool = False) -> None:
        cmd = ["git", "-C", str(self.base_repo), "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(self.path))
        subprocess.run(cmd, check=False, capture_output=True)
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)


def _git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def add_worktree(
    repo: str | Path,
    branch: str | None = None,
    base: str = "HEAD",
    parent_dir: str | Path | None = None,
) -> WorktreeHandle:
    """Create a new worktree off `base`. Returns handle with path + branch."""
    repo = Path(repo).resolve()
    if not (repo / ".git").exists() and not (repo / "HEAD").exists():
        raise ValueError(f"{repo} is not a git repository")
    branch = branch or f"agent/wt-{uuid.uuid4().hex[:8]}"
    parent = Path(parent_dir or repo.parent / ".agentic-worktrees").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    wt_path = parent / branch.replace("/", "_")
    _git(repo, "worktree", "add", "-b", branch, str(wt_path), base)
    return WorktreeHandle(path=wt_path, branch=branch, base_repo=repo)


def list_worktrees(repo: str | Path) -> list[dict[str, str]]:
    out = _git(Path(repo).resolve(), "worktree", "list", "--porcelain")
    blocks = [b for b in out.split("\n\n") if b.strip()]
    res = []
    for blk in blocks:
        d: dict[str, str] = {}
        for line in blk.splitlines():
            if " " in line:
                k, v = line.split(" ", 1)
                d[k] = v
            else:
                d[line] = ""
        res.append(d)
    return res
