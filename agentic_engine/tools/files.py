"""File and text-search tools."""
from __future__ import annotations

import fnmatch
import os
import re
import shutil
from pathlib import Path
from typing import Annotated, Literal

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


@tool(
    name="write_file",
    description="Write text to a file. Creates parent dirs. Configurable overwrite/backup.",
    requires_approval=True,
)
def write_file(
    path: str,
    content: str,
    if_exists: Annotated[
        Literal["overwrite", "fail", "append"],
        "What to do when the file already exists.",
    ] = "overwrite",
    backup: Annotated[bool, "If True, copy existing file to <path>.bak before writing."] = False,
) -> str:
    """Write `content` to `path`.

    Args:
        path: Target file path. ``~`` is expanded.
        content: Text content to write.
        if_exists: ``overwrite`` (default), ``fail`` (refuse), or ``append``.
        backup: Make a ``.bak`` copy first when the file exists.
    """
    p = Path(os.path.expanduser(path))
    try:
        existed = p.exists()
        if existed:
            if if_exists == "fail":
                return f"[refused] file exists and if_exists='fail': {p}"
            if backup:
                shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
        p.parent.mkdir(parents=True, exist_ok=True)
        if existed and if_exists == "append":
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
            return f"appended {len(content)} chars to {p}"
        p.write_text(content, encoding="utf-8")
        suffix = " (.bak created)" if (existed and backup) else ""
        return f"wrote {len(content)} chars to {p}{suffix}"
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


_DEFAULT_IGNORE = (
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".cache", "target",
)


def _is_ignored(rel: Path, ignores: tuple[str, ...]) -> bool:
    parts = rel.parts
    for ig in ignores:
        if "*" in ig or "?" in ig:
            if any(fnmatch.fnmatch(part, ig) for part in parts):
                return True
        elif ig in parts:
            return True
    return False


@tool(name="grep_text", description="Regex search through a directory of text files.", read_only=True)
def grep_text(
    pattern: str,
    path: str = ".",
    glob: str = "**/*",
    max_hits: int = 50,
    ignore: Annotated[
        list[str] | None,
        "Extra directory names or globs to skip on top of the defaults.",
    ] = None,
    include_hidden: bool = False,
) -> str:
    """Regex search across files. Skips common build/cache dirs by default."""
    p = Path(os.path.expanduser(path))
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"[error] bad regex: {e}"
    ignores = tuple(_DEFAULT_IGNORE) + tuple(ignore or ())
    hits: list[str] = []
    for f in p.glob(glob):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(p)
        except ValueError:
            rel = f
        if _is_ignored(rel, ignores):
            continue
        if not include_hidden and any(part.startswith(".") and part not in (".",)
                                      for part in rel.parts):
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
