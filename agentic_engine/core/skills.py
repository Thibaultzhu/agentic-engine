"""SkillRegistry — file-based plugin system. Each skill is a folder with SKILL.md.

SKILL.md layout (YAML frontmatter + markdown body):
    ---
    name: my-skill
    description: One-line third-person summary
    version: 1.0.0
    triggers:
      - "code review"
      - "review pr"
    ---

    # body — instructions / steps / pitfalls
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..config import get_settings


@dataclass
class Skill:
    name: str
    description: str
    version: str
    triggers: list[str] = field(default_factory=list)
    body: str = ""
    path: Path | None = None

    def matches(self, query: str) -> bool:
        q = query.lower()
        if any(t.lower() in q for t in self.triggers):
            return True
        return self.name.lower() in q


class SkillRegistry:
    def __init__(self, search_paths: list[Path] | None = None):
        s = get_settings()
        default_paths = [
            Path(__file__).resolve().parents[2] / "skills",  # repo skills/
            s.home / "skills",                                # user skills
            Path.cwd() / ".agentic" / "skills",               # project skills
        ]
        self.search_paths = [p for p in (search_paths or default_paths) if p.exists()]
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        for root in self.search_paths:
            for skill_md in root.glob("*/SKILL.md"):
                try:
                    skill = self._parse(skill_md)
                    self._skills[skill.name] = skill
                except Exception as e:
                    print(f"[skills] skip {skill_md}: {e}")

    @staticmethod
    def _parse(path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
        return Skill(
            name=meta.get("name") or path.parent.name,
            description=meta.get("description", ""),
            version=str(meta.get("version", "0.1.0")),
            triggers=list(meta.get("triggers") or []),
            body=body,
            path=path,
        )

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def find(self, query: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.matches(query)]
