"""Orchestrator — coordinates multiple Agents.

Modes:
    sequential : pipe agent_i.output → agent_{i+1}
    parallel   : run all in threads, return list[AgentResult]
    team       : leader delegates tasks to named members via dispatch()
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from rich.console import Console

from .agent import Agent, AgentResult


_console = Console()


@dataclass
class Orchestrator:
    agents: list[Agent] = field(default_factory=list)
    name: str = "orchestrator"

    def add(self, agent: Agent) -> "Orchestrator":
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
        verbose: bool = True,
        max_workers: int = 8,
    ) -> dict[str, AgentResult]:
        """prompts: {agent_name: prompt}. Agents must already be added."""
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
                f"You are the team lead. Decompose this goal into subtasks for your team and "
                f"output a JSON object {{member_name: subtask}} only.\n\nGoal: {goal}",
                verbose=verbose,
            )
            import json
            try:
                plan = json.loads(planning.output[planning.output.find("{"): planning.output.rfind("}") + 1])
            except Exception:
                plan = {a.name: goal for a in self.agents if a.name != leader_name}

        member_results = self.run_parallel(plan, verbose=verbose)
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
