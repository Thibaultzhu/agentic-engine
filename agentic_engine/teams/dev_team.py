"""5-role software-development team — a common reference composition.

PM → Architect → Developer → Reviewer → Tester
"""
from __future__ import annotations

from ..core.agent import Agent
from ..core.orchestrator import Orchestrator
from ..core.permissions import PermissionMode
from ..tools import bash_run, grep_text, list_dir, read_file, write_file


def build_dev_team(workdir: str = ".", model: str | None = None) -> Orchestrator:
    common = [read_file, list_dir, grep_text]
    pm = Agent(
        name="pm",
        role="product-manager",
        system_prompt=(
            "You are a senior product manager. Convert vague user goals into a crisp, "
            "numbered requirements list. Output only the list, no preamble."
        ),
        tools=common,
        model=model,
    )
    architect = Agent(
        name="architect",
        role="software-architect",
        system_prompt=(
            "You are a software architect. Given requirements, produce a module breakdown, "
            "data flow, and API surface in markdown. Be specific about file paths."
        ),
        tools=common,
        model=model,
    )
    dev = Agent(
        name="developer",
        role="developer",
        system_prompt=(
            "You are a senior developer. Given a module spec, write production-grade code. "
            "Use write_file to persist files. Follow PEP 8 and add docstrings."
        ),
        tools=[*common, write_file, bash_run],
        permission=PermissionMode.ACCEPT_EDITS,
        model=model,
        max_turns=12,
    )
    reviewer = Agent(
        name="reviewer",
        role="code-reviewer",
        system_prompt=(
            "You are a strict reviewer. Read every file the developer produced and report "
            "issues by file:line. Categorize as BUG / STYLE / SECURITY / PERF. "
            "End with PASS or REJECT."
        ),
        tools=common,
        model=model,
    )
    tester = Agent(
        name="tester",
        role="qa-engineer",
        system_prompt=(
            "You are a QA engineer. Write pytest tests covering happy + edge cases. "
            "Use write_file to save tests under tests/ and bash_run to execute them. "
            "Report PASS/FAIL summary."
        ),
        tools=[*common, write_file, bash_run],
        permission=PermissionMode.ACCEPT_EDITS,
        model=model,
        max_turns=12,
    )
    return Orchestrator(agents=[pm, architect, dev, reviewer, tester], name="dev-team")
