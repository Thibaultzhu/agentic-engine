"""Bash execution tool. Sandbox-aware via cwd; never auto-deletes."""
from __future__ import annotations

import shlex
import subprocess

from ..core.tool import tool

_DANGEROUS_TOKENS = {
    "mkfs", "mkfs.ext4", "mkfs.xfs", "mkfs.btrfs",
    "shutdown", "reboot", "halt", "poweroff",
    "dd",
}
_FORK_BOMB = ":(){"
_RM_FLAGS = {"-rf", "-fr", "-Rf", "-fR", "--recursive"}


def _looks_destructive(command: str) -> bool:
    if _FORK_BOMB in command:
        return True
    try:
        argv = shlex.split(command)
    except ValueError:
        # Unparseable — fall back to substring match.
        bad_substr = ("rm -rf /", "mkfs", "shutdown", "dd if=", _FORK_BOMB)
        return any(b in command for b in bad_substr)
    for i, tok in enumerate(argv):
        base = tok.rsplit("/", 1)[-1]
        if base in _DANGEROUS_TOKENS:
            return True
        if base == "rm":
            rest = set(argv[i + 1:])
            # rm -rf / or rm -rf ~ or rm -rf $HOME
            if rest & _RM_FLAGS and any(t in rest for t in ("/", "~", "$HOME", "/*", "~/*")):
                return True
    return False


@tool(
    name="bash_run",
    description="Run a shell command and return stdout/stderr. Avoid destructive commands.",
    requires_approval=True,
)
def bash_run(command: str, cwd: str = ".", timeout: int = 60) -> str:
    """Execute a shell command. Returns combined output (truncated to 8000 chars)."""
    if _looks_destructive(command):
        return "[refused] command looks destructive"
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = proc.stdout
        err = proc.stderr
        body = (out or "") + (("\n[stderr]\n" + err) if err else "")
        return body[:8000] or f"[exit={proc.returncode}, no output]"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except Exception as e:  # noqa: BLE001
        return f"[error] {type(e).__name__}: {e}"
