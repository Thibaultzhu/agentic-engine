"""Single-agent demo — chat with one agent that has file tools."""
from agentic_engine import Agent
from agentic_engine.tools import read_file, list_dir, grep_text, web_fetch


if __name__ == "__main__":
    a = Agent(
        name="solo",
        role="general-purpose",
        system_prompt="You are a helpful agent. Use tools when needed.",
        tools=[read_file, list_dir, grep_text, web_fetch],
    )
    a.run("List the current directory and tell me what kind of project this looks like.")
