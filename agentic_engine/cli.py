"""CLI entry point — `agentic <command>`."""
from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import get_settings
from .core.skills import SkillRegistry
from .core.memory import Memory


app = typer.Typer(help="agentic-engine CLI")
console = Console()


# -------- top-level --------
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


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(9120, "--port"),
) -> None:
    """Start the FastAPI HTTP server."""
    import uvicorn
    uvicorn.run("agentic_engine.server:app", host=host, port=port, reload=False)


# -------- sessions --------
sessions_app = typer.Typer(help="Manage projects / conversations")
app.add_typer(sessions_app, name="sessions")


@sessions_app.command("ls")
def sessions_ls(project_id: str | None = typer.Option(None, "--project")) -> None:
    from .core.sessions import SessionStore
    table = Table("id", "project", "title", "updated_at", "archived")
    for s in SessionStore().list_sessions(project_id):
        table.add_row(s.id, s.project_id, s.title, s.updated_at, str(s.archived))
    console.print(table)


@sessions_app.command("new")
def sessions_new(
    project: str = typer.Option("default", "--project"),
    root: str = typer.Option(".", "--root"),
    title: str = typer.Option("untitled", "--title"),
) -> None:
    from .core.sessions import SessionStore
    store = SessionStore()
    p = store.upsert_project(project, root)
    s = store.new_session(p.id, title)
    console.print(f"[green]created session[/] {s.id} (project={p.name})")


@sessions_app.command("show")
def sessions_show(sid: str) -> None:
    from .core.sessions import SessionStore
    for m in SessionStore().history(sid):
        console.print(f"[bold cyan]{m.role}[/] {m.created_at}\n{m.content}\n")


# -------- cron --------
cron_app = typer.Typer(help="Scheduled tasks (APScheduler)")
app.add_typer(cron_app, name="cron")


@cron_app.command("ls")
def cron_ls() -> None:
    from .core.cron import CronManager
    table = Table("id", "name", "schedule", "enabled")
    for j in CronManager().list():
        table.add_row(j.id, j.name, json.dumps(j.schedule, ensure_ascii=False), str(j.enabled))
    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Argument(...),
    cron_expr: str | None = typer.Option(None, "--cron", help="e.g. '0 9 * * *'"),
    interval: int | None = typer.Option(None, "--interval", help="seconds"),
    message: str = typer.Option(..., "--message", help="agent prompt to run"),
) -> None:
    from .core.cron import CronManager
    if cron_expr:
        sched = {"kind": "cron", "expr": cron_expr}
    elif interval:
        sched = {"kind": "interval", "seconds": interval}
    else:
        raise typer.BadParameter("provide --cron or --interval")
    job = CronManager().add(name, sched, {"type": "agent_turn", "message": message})
    console.print(f"[green]added[/] {job.id}")


@cron_app.command("rm")
def cron_rm(job_id: str) -> None:
    from .core.cron import CronManager
    ok = CronManager().remove(job_id)
    console.print("[green]removed[/]" if ok else "[red]not found[/]")


# -------- usage --------
@app.command()
def usage(
    days: int | None = typer.Option(None, "--days"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show token-usage summary."""
    from .core.usage import default_tracker
    s = default_tracker().summary(days=days)
    if json_out:
        console.print_json(data=s)
    else:
        console.print(f"calls         : {s['calls']}")
        console.print(f"prompt tokens : {s['prompt_tokens']}")
        console.print(f"compl. tokens : {s['completion_tokens']}")
        console.print(f"total tokens  : {s['total_tokens']}")
        console.print(f"cost (CNY)    : {s['cost_cny']}")
        if s["by_model"]:
            t = Table("model", "calls", "prompt", "completion", "cost")
            for m, v in s["by_model"].items():
                t.add_row(m, str(v["calls"]), str(v["prompt"]), str(v["completion"]), f"{v['cost']:.4f}")
            console.print(t)


# -------- worktree --------
worktree_app = typer.Typer(help="git worktree helpers for parallel agents")
app.add_typer(worktree_app, name="worktree")


@worktree_app.command("add")
def wt_add(
    repo: str = typer.Argument("."),
    branch: str | None = typer.Option(None, "--branch"),
    base: str = typer.Option("HEAD", "--base"),
) -> None:
    from .core.worktree import add_worktree
    h = add_worktree(repo, branch=branch, base=base)
    console.print(f"[green]created[/] {h.path} ({h.branch})")


@worktree_app.command("ls")
def wt_ls(repo: str = typer.Argument(".")) -> None:
    from .core.worktree import list_worktrees
    for w in list_worktrees(repo):
        console.print(w)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
