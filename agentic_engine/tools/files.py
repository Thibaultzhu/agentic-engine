"""File and text-search tools."""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..core.tool import tool


@tool(name="read_file", description="Read a text file. Returns content (truncated).", read_only=True)
def read_file(path: str, max_chars: int = 8000) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"[error] not found: {path}"
    if not p.is_file():
        return f"[error] not a file: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]
    except Exception as e:  # noqa: BLE001
        return f"[error] {type(e).__name__}: {e}"


@tool(name="write_file", description="Write text to a file. Creates parent dirs. Overwrites.", requires_approval=True)
def write_file(path: str, content: str) -> str:
    p = Path(os.path.expanduser(path))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {p}"
    except Exception as e:  # noqa: BLE001
        return f"[error] {type(e).__name__}: {e}"


@tool(name="list_dir", description="List a directory's entries (non-recursive).", read_only=True)
def list_dir(path: str = ".") -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"[error] not found: {path}"
    entries = []
    for item in sorted(p.iterdir()):
        kind = "d" if item.is_dir() else "f"
        entries.append(f"{kind} {item.name}")
    return "\n".join(entries) or "[empty]"


@tool(name="grep_text", description="Regex search through a directory of text files.", read_only=True)
def grep_text(pattern: str, path: str = ".", glob: str = "**/*", max_hits: int = 50) -> str:
    p = Path(os.path.expanduser(path))
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"[error] bad regex: {e}"
    hits: list[str] = []
    for f in p.glob(glob):
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f}:{i}: {line.strip()[:200]}")
                    if len(hits) >= max_hits:
                        return "\n".join(hits) + f"\n[truncated at {max_hits}]"
        except Exception:
            continue
    return "\n".join(hits) or "[no matches]"
