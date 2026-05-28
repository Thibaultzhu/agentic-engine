"""Bash execution tool. Sandbox-aware via cwd; never auto-deletes.

Hardening (v0.3):

- ``AGENTIC_BASH_CWD_ALLOW`` — colon-separated list of permitted cwd prefixes
  (resolved). Empty / unset → only the current working directory is allowed.
- ``AGENTIC_BASH_TIMEOUT_MAX`` — caps per-call ``timeout`` (default 300).
- ``AGENTIC_BASH_OUTPUT_MAX`` — caps stdout+stderr length (default 8000).
- ``AGENTIC_BASH_RLIMIT_MEM_MB`` — POSIX ``setrlimit(RLIMIT_AS, …)`` cap
  applied via ``preexec_fn`` (default 1024). 0 disables.
- ``AGENTIC_BASH_RLIMIT_CPU_S`` — POSIX ``setrlimit(RLIMIT_CPU, …)`` cap
  (default = ``timeout`` of the call). 0 disables.
- Optional sandbox wrappers picked up automatically when present:
    Linux  → ``bwrap`` (read-only ``/`` + RW cwd) when on PATH and
             ``AGENTIC_BASH_USE_BWRAP=1``.
    macOS  → ``sandbox-exec`` profile that allows file-read/write only to
             cwd and disallows network, when ``AGENTIC_BASH_USE_SBX=1``.
"""
from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

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
        bad_substr = ("rm -rf /", "mkfs", "shutdown", "dd if=", _FORK_BOMB)
        return any(b in command for b in bad_substr)
    for i, tok in enumerate(argv):
        base = tok.rsplit("/", 1)[-1]
        if base in _DANGEROUS_TOKENS:
            return True
        if base == "rm":
            rest = set(argv[i + 1:])
            if rest & _RM_FLAGS and any(t in rest for t in ("/", "~", "$HOME", "/*", "~/*")):
                return True
    return False


def _resolve(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _cwd_allowed(cwd: str) -> bool:
    """Return True iff ``cwd`` is inside any allowlist prefix.

    The allowlist source is ``AGENTIC_BASH_CWD_ALLOW`` (colon-separated).
    Without an explicit allowlist we accept the process cwd or any sub-path
    beneath it, plus the system temp directory (so pytest tmp_path works
    out of the box) — no chdir into ``/`` or another user's home.
    """
    import tempfile

    target = _resolve(cwd)
    raw = os.environ.get("AGENTIC_BASH_CWD_ALLOW", "")
    prefixes = [Path(p).expanduser().resolve() for p in raw.split(":") if p.strip()]
    if not prefixes:
        prefixes = [_resolve("."), _resolve(tempfile.gettempdir())]
        # macOS: /tmp -> /private/tmp; ensure both forms are accepted.
        for extra in ("/tmp", "/private/tmp", "/private/var/folders"):
            with contextlib.suppress(OSError):
                prefixes.append(_resolve(extra))
    return any(target == p or p in target.parents for p in prefixes)


def _preexec(timeout: int) -> Any:
    """Apply RLIMIT_AS / RLIMIT_CPU after fork. Returns a callable or ``None``."""
    if os.name != "posix":
        return None
    mem_mb = int(os.environ.get("AGENTIC_BASH_RLIMIT_MEM_MB", "1024"))
    cpu_s = int(os.environ.get("AGENTIC_BASH_RLIMIT_CPU_S", str(timeout)))

    def _apply() -> None:  # pragma: no cover — runs after fork
        try:
            import resource

            if mem_mb > 0:
                bytes_ = mem_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (bytes_, bytes_))
            if cpu_s > 0:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
            # New process group → can be killed cleanly on timeout.
            os.setsid()
        except Exception:
            pass

    return _apply


def _wrap_sandbox(command: str, cwd: str) -> tuple[list[str] | None, str | None]:
    """Return (argv, shell_flag) for the sandboxed command, or (None, None)."""
    if os.name == "posix" and sys.platform.startswith("linux"):
        if os.environ.get("AGENTIC_BASH_USE_BWRAP") == "1" and shutil.which("bwrap"):
            argv = [
                "bwrap",
                "--ro-bind", "/", "/",
                "--bind", cwd, cwd,
                "--proc", "/proc",
                "--dev", "/dev",
                "--unshare-net",  # no network by default
                "sh", "-c", command,
            ]
            return argv, None
    if sys.platform == "darwin" and os.environ.get("AGENTIC_BASH_USE_SBX") == "1":
        if shutil.which("sandbox-exec"):
            profile = (
                "(version 1)"
                "(deny default)"
                '(allow process-fork)(allow process-exec)'
                '(allow file-read*)'
                f'(allow file-write* (subpath "{_resolve(cwd)}"))'
                "(allow signal (target self))"
                "(allow sysctl-read)(allow mach-lookup)(allow ipc-posix*)"
            )
            argv = ["sandbox-exec", "-p", profile, "sh", "-c", command]
            return argv, None
    return None, None


@tool(
    name="bash_run",
    description="Run a shell command and return stdout/stderr. Avoid destructive commands.",
    requires_approval=True,
)
def bash_run(command: str, cwd: str = ".", timeout: int = 60) -> str:
    """Execute a shell command. Returns combined output (truncated)."""
    if _looks_destructive(command):
        return "[refused] command looks destructive"
    timeout_max = int(os.environ.get("AGENTIC_BASH_TIMEOUT_MAX", "300"))
    timeout = max(1, min(timeout, timeout_max))
    if not _cwd_allowed(cwd):
        return f"[refused] cwd '{cwd}' not in AGENTIC_BASH_CWD_ALLOW"
    out_max = int(os.environ.get("AGENTIC_BASH_OUTPUT_MAX", "8000"))

    argv, _ = _wrap_sandbox(command, cwd)
    try:
        if argv is not None:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_preexec(timeout),
            )
        else:
            proc = subprocess.run(  # noqa: S602  # nosec B602 — intentional shell tool, gated by allowlist + destructive-token blocker + rlimits
                command,
                shell=True,  # noqa: S602
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_preexec(timeout),
            )
        out = proc.stdout
        err = proc.stderr
        body = (out or "") + (("\n[stderr]\n" + err) if err else "")
        return body[:out_max] or f"[exit={proc.returncode}, no output]"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except Exception as e:  # noqa: BLE001
        return f"[error] {type(e).__name__}: {e}"
