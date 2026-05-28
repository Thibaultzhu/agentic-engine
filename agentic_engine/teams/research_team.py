"""3-role research team — Scout → Analyst → Reporter."""
from __future__ import annotations

from ..core.agent import Agent
from ..core.orchestrator import Orchestrator
from ..tools import web_fetch, read_file, write_file, grep_text


def build_research_team(model: str | None = None) -> Orchestrator:
    scout = Agent(
        name="scout",
        role="research-scout",
        system_prompt=(
            "You collect raw material. Fetch up to 5 URLs related to the topic and return "
            "their key passages verbatim with the source URL above each."
        ),
        tools=[web_fetch, read_file, grep_text],
        model=model,
    )
    analyst = Agent(
        name="analyst",
        role="analyst",
        system_prompt=(
            "You read the scout's notes and synthesize: identify themes, contradictions, "
            "and the 3 most actionable insights. Output structured markdown."
        ),
        tools=[read_file, grep_text],
        model=model,
    )
    reporter = Agent(
        name="reporter",
        role="reporter",
        system_prompt=(
            "Write a tight executive briefing (≤500 words) from the analyst's synthesis. "
            "Use write_file to save to outputs/briefing.md."
        ),
        tools=[write_file],
        model=model,
    )
    return Orchestrator(agents=[scout, analyst, reporter], name="research-team")
