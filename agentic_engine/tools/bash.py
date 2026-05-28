"""Bash execution tool. Sandbox-aware via cwd; never auto-deletes."""
from __future__ import annotations

import subprocess

from ..core.tool import tool


@tool(
    name="bash_run",
    description="Run a shell command and return stdout/stderr. Avoid destructive commands.",
    requires_approval=True,
)
def bash_run(command: str, cwd: str = ".", timeout: int = 60) -> str:
    """Execute a shell command. Returns combined output (truncated to 8000 chars)."""
    banned = ("rm -rf /", "mkfs", ":(){", "shutdown", "dd if=")
    if any(b in command for b in banned):
        return f"[refused] command contains banned pattern"
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
