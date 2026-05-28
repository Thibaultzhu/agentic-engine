"""CLI entry point — `agentic <command>`."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import get_settings
from .core.skills import SkillRegistry
from .core.memory import Memory


app = typer.Typer(help="agentic-engine CLI")
console = Console()


@app.command()
def version() -> None:
    """Show version + active region."""
    s = get_settings()
    console.print(f"agentic-engine [bold]{__version__}[/]")
    console.print(f"region    : {s.region}")
    console.print(f"base_url  : {s.base_url}")
    console.print(f"model     : {s.model_default}")
    console.print(f"home      : {s.home}")


@app.command()
def chat(
    message: str = typer.Argument(..., help="user prompt"),
    model: str | None = typer.Option(None, "--model", "-m"),
    role: str = typer.Option("general-purpose", "--role"),
) -> None:
    """One-shot single-agent chat."""
    from .core.agent import Agent
    from .tools import read_file, list_dir, grep_text, web_fetch

    a = Agent(
        name="solo",
        role=role,
        tools=[read_file, list_dir, grep_text, web_fetch],
        model=model,
    )
    a.run(message)


@app.command("dev-team")
def dev_team(
    goal: str = typer.Argument(..., help="What to build"),
    model: str | None = typer.Option(None, "--model", "-m"),
) -> None:
    """Run the 5-role dev team end-to-end (sequential)."""
    from .teams import build_dev_team

    team = build_dev_team(model=model)
    results = team.run_sequential(goal)
    console.rule("[bold green]final outputs[/]")
    for r in results:
        console.print(f"[bold]{r.agent}[/] (turns={r.turns}, tools={r.tool_calls})")
        console.print(r.output[:500])


@app.command()
def skills() -> None:
    """List available skills."""
    reg = SkillRegistry()
    table = Table("name", "version", "description", "path")
    for s in reg.list():
        table.add_row(s.name, s.version, s.description[:60], str(s.path))
    console.print(table)


@app.command()
def memory(
    action: str = typer.Argument("show", help="show | add | search"),
    scope: str = typer.Option("user", "--scope"),
    text: str | None = typer.Option(None, "--text"),
) -> None:
    """Inspect or update persistent memory."""
    m = Memory()
    if action == "show":
        console.print(m.read(scope))
    elif action == "add":
        if not text:
            raise typer.BadParameter("--text required for add")
        m.add(scope, text)
        console.print(f"[green]added to {scope}[/]")
    elif action == "search":
        if not text:
            raise typer.BadParameter("--text required for search")
        for sc, line in m.search(text):
            console.print(f"[cyan]{sc}[/] {line}")
    else:
        raise typer.BadParameter("unknown action")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
