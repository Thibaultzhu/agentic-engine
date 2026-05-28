"""Dev-team demo — sequential 5-role pipeline builds a tiny CLI tool."""
from agentic_engine.teams import build_dev_team


if __name__ == "__main__":
    team = build_dev_team(model=None)  # use default qwen-plus
    goal = (
        "Build a tiny Python CLI named 'wcli' that takes a file path and prints "
        "lines/words/chars counts. Save it under workdir/wcli/. Include a pytest test."
    )
    results = team.run_sequential(goal)
    print("\n========== TEAM SUMMARY ==========")
    for r in results:
        print(f"[{r.agent}] turns={r.turns}, tool_calls={r.tool_calls}")
