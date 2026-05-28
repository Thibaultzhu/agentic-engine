"""Eval harness — golden-task pass/fail runner with cost tracking.

Tasks are JSON files (or in-memory dicts) with this shape::

    {
      "name": "json-extraction",
      "input": "extract the json from this: ```json {\\"x\\":1}```",
      "expect": {
        "kind": "regex",
        "value": "x.*1"
      },
      "rubric": "the answer must contain x:1"
    }

``expect.kind`` may be ``regex``, ``contains`` (case-insensitive substring)
or ``llm`` (rubric judged by a second LLM call against ``rubric``).

Public API::

    from agentic_engine.evals import run_eval, load_tasks
    report = run_eval(tasks=load_tasks("evals/golden"), agent_factory=...)
    print(report.pass_rate)
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core.agent import Agent
from .llm import chat


@dataclass
class Task:
    name: str
    input: str
    expect: dict[str, Any]
    rubric: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        return cls(name=d["name"], input=d["input"], expect=d["expect"], rubric=d.get("rubric", ""))


@dataclass
class TaskResult:
    name: str
    passed: bool
    output: str
    elapsed: float
    note: str = ""


@dataclass
class EvalReport:
    results: list[TaskResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    @property
    def total_elapsed(self) -> float:
        return sum(r.elapsed for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_rate": round(self.pass_rate, 4),
            "total_elapsed_s": round(self.total_elapsed, 3),
            "n": len(self.results),
            "results": [r.__dict__ for r in self.results],
        }


def load_tasks(path: str | Path) -> list[Task]:
    """Load all ``*.json`` files under ``path`` (file or directory)."""
    p = Path(path)
    files: list[Path] = []
    if p.is_dir():
        files = sorted(p.glob("*.json"))
    elif p.is_file():
        files = [p]
    out: list[Task] = []
    for f in files:
        data = json.loads(f.read_text())
        if isinstance(data, list):
            out.extend(Task.from_dict(d) for d in data)
        else:
            out.append(Task.from_dict(data))
    return out


def _judge(output: str, expect: dict[str, Any], rubric: str) -> tuple[bool, str]:
    kind = expect.get("kind", "contains")
    val = expect.get("value", "")
    if kind == "regex":
        return bool(re.search(val, output, flags=re.S | re.I)), f"regex={val!r}"
    if kind == "contains":
        return val.lower() in (output or "").lower(), f"contains={val!r}"
    if kind == "llm":  # pragma: no cover — costs tokens, opt-in
        prompt = (
            "You are a strict grader. Given a rubric and a candidate answer, "
            "respond with exactly 'PASS' or 'FAIL' on the first line, then a "
            "one-line reason.\n\n"
            f"Rubric: {rubric}\n\nAnswer:\n{output}\n"
        )
        resp = chat([{"role": "user", "content": prompt}], temperature=0.0)
        verdict = resp.choices[0].message.content or "FAIL"
        return verdict.strip().upper().startswith("PASS"), verdict.strip()
    return False, f"unknown expect.kind={kind!r}"


def run_eval(
    tasks: list[Task],
    agent_factory: Callable[[], Agent] | None = None,
    runner: Callable[[str], str] | None = None,
) -> EvalReport:
    """Run every task either via ``runner(input)`` or a fresh ``Agent`` per task."""
    if runner is None and agent_factory is None:
        raise ValueError("provide either runner= or agent_factory=")
    report = EvalReport()
    for t in tasks:
        t0 = time.time()
        try:
            if runner:
                output = runner(t.input)
            else:
                agent = agent_factory()  # type: ignore[misc]
                output = agent.run(t.input, verbose=False).output
            passed, note = _judge(output, t.expect, t.rubric)
        except Exception as e:  # noqa: BLE001
            output, passed, note = f"[error] {e}", False, "exception"
        report.results.append(
            TaskResult(name=t.name, passed=passed, output=output[:1000],
                       elapsed=time.time() - t0, note=note)
        )
    return report


__all__ = ["Task", "TaskResult", "EvalReport", "load_tasks", "run_eval"]
