"""Optional FastAPI HTTP server — exposes /chat and /dev-team endpoints.

Run:  uvicorn agentic_engine.server:app --port 9120
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .core.agent import Agent
from .teams import build_dev_team
from .tools import read_file, list_dir, grep_text, web_fetch


app = FastAPI(title="agentic-engine", version="0.1.0")


class ChatReq(BaseModel):
    message: str
    role: str = "general-purpose"
    model: str | None = None


class DevTeamReq(BaseModel):
    goal: str
    model: str | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/chat")
def chat(req: ChatReq) -> dict:
    a = Agent(
        name="api-solo",
        role=req.role,
        tools=[read_file, list_dir, grep_text, web_fetch],
        model=req.model,
    )
    res = a.run(req.message, verbose=False)
    return {"output": res.output, "turns": res.turns, "tool_calls": res.tool_calls}


@app.post("/dev-team")
def dev_team(req: DevTeamReq) -> dict:
    team = build_dev_team(model=req.model)
    results = team.run_sequential(req.goal, verbose=False)
    return {"results": [{"agent": r.agent, "output": r.output, "turns": r.turns} for r in results]}
