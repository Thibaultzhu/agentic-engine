"""Permission modes — governs how an Agent handles risky operations.

In addition to the simple :class:`PermissionMode` enum, v0.3 introduces a
:class:`PermissionPolicy` engine that supports rule-based allow/deny
decisions on tool calls, with glob-style argument matching.
"""
from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal


class PermissionMode(str, Enum):
    DEFAULT = "default"            # Ask user for risky actions
    PLAN = "plan"                  # Every action requires explicit approval
    ACCEPT_EDITS = "accept_edits"  # Auto-accept file edits, ask others
    BYPASS = "bypass"              # Skip all checks (dangerous)
    DONT_ASK = "dont_ask"          # Reject anything not pre-approved


Decision = Literal["allow", "deny", "ask"]


@dataclass
class Rule:
    """One row in a permission policy.

    ``tool`` and arg patterns use :func:`fnmatch.fnmatchcase` (so
    ``bash_run``, ``write_*``, ``*`` all work). ``args`` is a mapping of
    argument-name → glob; *all* listed args must match for the rule to fire.
    """
    tool: str
    decision: Decision
    args: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def matches(self, tool_name: str, call_args: dict[str, Any]) -> bool:
        if not fnmatch.fnmatchcase(tool_name, self.tool):
            return False
        for k, pattern in self.args.items():
            value = call_args.get(k)
            if value is None or not fnmatch.fnmatchcase(str(value), pattern):
                return False
        return True


@dataclass
class PermissionPolicy:
    """Ordered list of :class:`Rule` plus a default decision.

    First matching rule wins. ``default`` is taken when no rule matches.
    """
    rules: list[Rule] = field(default_factory=list)
    default: Decision = "ask"
    remembered: dict[str, Decision] = field(default_factory=dict)

    def decide(self, tool_name: str, call_args: dict[str, Any]) -> Decision:
        # Session-level "remember this choice" (key = tool name only).
        if tool_name in self.remembered:
            return self.remembered[tool_name]
        for r in self.rules:
            if r.matches(tool_name, call_args):
                return r.decision
        return self.default

    def remember(self, tool_name: str, decision: Decision) -> None:
        self.remembered[tool_name] = decision

    # ---------- I/O ----------
    @classmethod
    def from_file(cls, path: str | Path) -> PermissionPolicy:
        p = Path(path).expanduser()
        if not p.exists():
            return cls()
        data = json.loads(p.read_text())
        rules = [Rule(**r) for r in data.get("rules", [])]
        return cls(rules=rules, default=data.get("default", "ask"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "default": self.default,
            "rules": [
                {"tool": r.tool, "decision": r.decision, "args": r.args, "note": r.note}
                for r in self.rules
            ],
        }


def default_policy() -> PermissionPolicy:
    """Load the policy from ``${AGENTIC_HOME}/permissions.json`` if present."""
    home = Path(os.environ.get("AGENTIC_HOME", str(Path.home() / ".agentic-engine")))
    return PermissionPolicy.from_file(home / "permissions.json")


__all__ = ["PermissionMode", "PermissionPolicy", "Rule", "Decision", "default_policy"]
