"""Memory — file-based persistent knowledge across sessions.

Four scopes (industry-standard pattern, also seen in CrewAI / AutoGen):
  - user      : profile/preferences/skills
  - feedback  : user corrections of agent behavior
  - project   : project-context not derivable from code/git
  - reference : pointers to external resources

Files live under {home}/memory/{scope}.md, plus daily logs under
{home}/memory/daily/YYYY-MM-DD.md for raw scratch.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from ..config import get_settings


_VALID = {"user", "feedback", "project", "reference"}


class Memory:
    def __init__(self, base: Path | None = None):
        s = get_settings()
        self.base = (base or s.home) / "memory"
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "daily").mkdir(exist_ok=True)
        for scope in _VALID:
            f = self.base / f"{scope}.md"
            if not f.exists():
                f.write_text(f"# {scope.title()} Memory\n\n", encoding="utf-8")

    def _path(self, scope: str) -> Path:
        if scope not in _VALID:
            raise ValueError(f"unknown scope: {scope}")
        return self.base / f"{scope}.md"

    # ---------- write ----------
    def add(self, scope: str, content: str) -> None:
        p = self._path(scope)
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n- [{ts}] {content.strip()}\n")

    def replace(self, scope: str, old: str, new: str) -> bool:
        p = self._path(scope)
        text = p.read_text(encoding="utf-8")
        if old not in text:
            return False
        p.write_text(text.replace(old, new, 1), encoding="utf-8")
        return True

    def remove(self, scope: str, snippet: str) -> bool:
        p = self._path(scope)
        text = p.read_text(encoding="utf-8")
        new = "\n".join(line for line in text.splitlines() if snippet not in line)
        if new == text:
            return False
        p.write_text(new + "\n", encoding="utf-8")
        return True

    def daily(self, content: str) -> Path:
        today = _dt.date.today().isoformat()
        p = self.base / "daily" / f"{today}.md"
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n## {ts}\n{content.strip()}\n")
        return p

    # ---------- read ----------
    def read(self, scope: str) -> str:
        return self._path(scope).read_text(encoding="utf-8")

    def search(self, query: str, scopes: list[str] | None = None) -> list[tuple[str, str]]:
        """Naive substring search. Returns (scope, line) hits."""
        targets = scopes or list(_VALID)
        hits: list[tuple[str, str]] = []
        q = query.lower()
        for scope in targets:
            for line in self._path(scope).read_text(encoding="utf-8").splitlines():
                if q in line.lower():
                    hits.append((scope, line.strip()))
        return hits

    def bootstrap_block(self) -> str:
        """Concatenate all scopes — inject as a system message at session start."""
        out = []
        for scope in ("user", "project", "feedback", "reference"):
            txt = self.read(scope).strip()
            if txt:
                out.append(f"[{scope}]\n{txt}")
        return "\n\n".join(out)
