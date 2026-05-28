"""Parallel research demo — 3 agents explore in parallel."""
from agentic_engine import Agent, Orchestrator
from agentic_engine.tools import web_fetch, grep_text, read_file


if __name__ == "__main__":
    def make(name: str, focus: str) -> Agent:
        return Agent(
            name=name,
            role="research-scout",
            system_prompt=f"You research the topic from the angle of: {focus}. "
                          f"Use web_fetch when given a URL. Output bullet points.",
            tools=[web_fetch, read_file, grep_text],
        )

    orch = Orchestrator(agents=[
        make("frontend", "frontend frameworks"),
        make("backend", "backend frameworks"),
        make("devops", "deployment platforms"),
    ])

    topic = "What are popular full-stack starter kits in 2026?"
    results = orch.run_parallel({
        "frontend": topic + " — focus on frontend.",
        "backend":  topic + " — focus on backend.",
        "devops":   topic + " — focus on deployment.",
    })
    for name, r in results.items():
        print(f"\n=== {name} ===\n{r.output}")
