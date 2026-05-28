"""Orchestrator — coordinates multiple Agents.

Modes:
    sequential : pipe agent_i.output → agent_{i+1}
    parallel   : run all in threads, return list[AgentResult]
    team       : leader delegates tasks to named members via dispatch()
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from .agent import Agent, AgentResult

_console = Console()
logger = logging.getLogger(__name__)


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict | None:
    """Best-effort: extract a JSON object from arbitrary LLM output.

    Tries, in order:
        1. raw json.loads on the full text (it might already be JSON).
        2. ```json ...``` fenced block.
        3. Bracket-balanced scan that respects strings & escapes.
    Returns None if nothing parseable is found.
    """
    if not text:
        return None
    text = text.strip()
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except Exception:
        pass

    m = _FENCE_RE.search(text)
    if m:
        try:
            v = json.loads(m.group(1))
            return v if isinstance(v, dict) else None
        except Exception:
            pass

    # Stack-based extractor: find the first balanced {...} that parses.
    n = len(text)
    for start in range(n):
        if text[start] != "{":
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, n):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        v = json.loads(candidate)
                        if isinstance(v, dict):
                            return v
                    except Exception:
                        break
    return None


@dataclass
class Orchestrator:
    agents: list[Agent] = field(default_factory=list)
    name: str = "orchestrator"

    def add(self, agent: Agent) -> Orchestrator:
        self.agents.append(agent)
        return self

    def by_name(self, name: str) -> Agent | None:
        for a in self.agents:
            if a.name == name:
                return a
        return None

    # ---------- sequential ----------
    def run_sequential(
        self,
        initial_input: str,
        glue: Callable[[AgentResult], str] | None = None,
        verbose: bool = True,
    ) -> list[AgentResult]:
        results: list[AgentResult] = []
        carry = initial_input
        for ag in self.agents:
            if verbose:
                _console.rule(f"[bold magenta]> {ag.name}")
            res = ag.run(carry, verbose=verbose)
            results.append(res)
            carry = glue(res) if glue else res.output
        return results

    # ---------- parallel ----------
    def run_parallel(
        self,
        prompts: dict[str, str],
        verbose: bool = False,
        max_workers: int = 8,
    ) -> dict[str, AgentResult]:
        """prompts: {agent_name: prompt}. Agents must already be added.

        Note: verbose defaults to False here because interleaved rich.Console
        output from many threads is unreadable. Set verbose=True only when
        you have one worker, or pipe each Agent through its own Console.
        """
        out: dict[str, AgentResult] = {}
        if not prompts:
            return out
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {}
            for name, prompt in prompts.items():
                ag = self.by_name(name)
                if not ag:
                    out[name] = AgentResult(agent=name, output=f"[error] agent {name} not found")
                    continue
                futures[ex.submit(ag.run, prompt, verbose)] = name
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    out[name] = fut.result()
                except Exception as e:  # noqa: BLE001
                    out[name] = AgentResult(agent=name, output=f"[error] {e}")
        return out

    # ---------- team-mode dispatch ----------
    def dispatch(
        self,
        leader_name: str,
        goal: str,
        plan: dict[str, str] | None = None,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Leader receives goal, optionally a plan {member: subtask}; members run in parallel.
        Leader then runs once more to consolidate the results.
        """
        leader = self.by_name(leader_name)
        if not leader:
            return {"error": f"leader '{leader_name}' not found"}

        if not plan:
            planning = leader.run(
                "You are the team lead. Decompose this goal into subtasks for your team and "
                "output a JSON object {member_name: subtask} only. Do NOT wrap it in prose.\n\n"
                f"Goal: {goal}",
                verbose=verbose,
            )
            extracted = _extract_json_object(planning.output)
            if extracted and all(isinstance(v, str) for v in extracted.values()):
                plan = extracted
            else:
                logger.warning("[dispatch] could not parse plan, falling back to fan-out")
                plan = {a.name: goal for a in self.agents if a.name != leader_name}

        member_results = self.run_parallel(plan, verbose=False)
        summary_input = (
            f"Goal: {goal}\n\nTeam outputs:\n" +
            "\n\n".join(f"## {n}\n{r.output}" for n, r in member_results.items())
        )
        final = leader.run(
            f"Consolidate these team outputs into a final answer for the user.\n\n{summary_input}",
            verbose=verbose,
        )
        return {
            "plan": plan,
            "members": {n: r.output for n, r in member_results.items()},
            "final": final.output,
        }
