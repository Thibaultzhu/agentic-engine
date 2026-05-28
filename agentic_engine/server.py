"""FastAPI HTTP server.

Endpoints:
    GET  /health
    POST /chat
    POST /dev-team
    GET  /usage                       — usage summary
    GET  /sessions                    — list sessions
    POST /sessions                    — create session
    POST /sessions/{sid}/append       — append message
    GET  /sessions/{sid}              — list messages
    GET  /cron                        — list jobs
    POST /cron                        — add job
    DELETE /cron/{job_id}             — remove job

H5 access:
    POST /h5/token                    — issue one-time token (header: X-Admin-Key)
    GET  /h5/page?token=...           — minimal HTML chat page
    WS   /h5/ws?token=...             — websocket bridge (optional)

Run:  uvicorn agentic_engine.server:app --port 9120
"""
from __future__ import annotations

import os
import secrets
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .core.agent import Agent
from .core.cron import CronManager
from .core.sessions import SessionStore
from .core.usage import default_tracker
from .teams import build_dev_team
from .tools import read_file, list_dir, grep_text, web_fetch


app = FastAPI(title="agentic-engine", version="0.2.0")
_store = SessionStore()
_cron = CronManager()
_tokens: dict[str, float] = {}  # token -> expiry epoch


# ============= Models =============
class ChatReq(BaseModel):
    message: str
    role: str = "general-purpose"
    model: str | None = None
    session_id: str | None = None


class DevTeamReq(BaseModel):
    goal: str
    model: str | None = None


class SessionCreateReq(BaseModel):
    project_name: str = "default"
    project_root: str = "."
    title: str = "untitled"


class AppendReq(BaseModel):
    role: str
    content: str


class CronAddReq(BaseModel):
    name: str
    schedule: dict[str, Any]
    payload: dict[str, Any]


# ============= Health / Chat =============
@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": "0.2.0"}


@app.post("/chat")
def chat(req: ChatReq) -> dict:
    a = Agent(
        name="api-solo",
        role=req.role,
        tools=[read_file, list_dir, grep_text, web_fetch],
        model=req.model,
    )
    res = a.run(req.message, verbose=False)
    if req.session_id:
        _store.append(req.session_id, "user", req.message)
        _store.append(req.session_id, "assistant", res.output)
    return {"output": res.output, "turns": res.turns, "tool_calls": res.tool_calls}


@app.post("/dev-team")
def dev_team(req: DevTeamReq) -> dict:
    team = build_dev_team(model=req.model)
    results = team.run_sequential(req.goal, verbose=False)
    return {"results": [{"agent": r.agent, "output": r.output, "turns": r.turns} for r in results]}


# ============= Usage =============
@app.get("/usage")
def usage(days: int | None = None) -> dict:
    return default_tracker().summary(days=days)


# ============= Sessions =============
@app.get("/sessions")
def list_sessions(project_id: str | None = None) -> dict:
    items = _store.list_sessions(project_id=project_id)
    return {"sessions": [s.__dict__ for s in items]}


@app.post("/sessions")
def create_session(req: SessionCreateReq) -> dict:
    proj = _store.upsert_project(req.project_name, req.project_root)
    s = _store.new_session(proj.id, req.title)
    return {"project": proj.__dict__, "session": s.__dict__}


@app.post("/sessions/{sid}/append")
def session_append(sid: str, req: AppendReq) -> dict:
    m = _store.append(sid, req.role, req.content)
    return {"message": m.__dict__}


@app.get("/sessions/{sid}")
def session_history(sid: str) -> dict:
    msgs = _store.history(sid)
    return {"messages": [m.__dict__ for m in msgs]}


# ============= Cron =============
@app.get("/cron")
def cron_list() -> dict:
    return {"jobs": [j.__dict__ for j in _cron.list()]}


@app.post("/cron")
def cron_add(req: CronAddReq) -> dict:
    job = _cron.add(req.name, req.schedule, req.payload)
    return {"job": job.__dict__}


@app.delete("/cron/{job_id}")
def cron_remove(job_id: str) -> dict:
    ok = _cron.remove(job_id)
    return {"removed": ok}


# ============= H5 =============
def _verify_admin(key: str | None) -> None:
    expected = os.getenv("AGENTIC_ADMIN_KEY", "")
    if not expected or key != expected:
        raise HTTPException(status_code=401, detail="bad admin key")


@app.post("/h5/token")
def h5_issue_token(x_admin_key: str | None = Header(default=None), ttl: int = 1800) -> dict:
    _verify_admin(x_admin_key)
    tok = secrets.token_urlsafe(24)
    _tokens[tok] = time.time() + ttl
    return {"token": tok, "ttl": ttl}


def _check_token(tok: str) -> bool:
    exp = _tokens.get(tok)
    if not exp:
        return False
    if time.time() > exp:
        _tokens.pop(tok, None)
        return False
    return True


@app.get("/h5/page", response_class=HTMLResponse)
def h5_page(token: str) -> str:
    if not _check_token(token):
        return HTMLResponse("<h3>Token invalid or expired.</h3>", status_code=401)
    return HTMLResponse(f"""
<!DOCTYPE html><html><head><meta charset='utf-8'><title>agentic-engine H5</title>
<meta name='viewport' content='width=device-width,initial-scale=1'></head>
<body style='font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:680px;margin:1em auto;padding:1em'>
<h2>agentic-engine</h2>
<div id='log' style='border:1px solid #ddd;border-radius:8px;padding:10px;height:60vh;overflow:auto;background:#fafafa'></div>
<form id='f' style='display:flex;gap:8px;margin-top:10px'>
  <input id='m' style='flex:1;padding:10px;border:1px solid #ccc;border-radius:8px' placeholder='Ask anything...' autofocus>
  <button style='padding:10px 16px;border:0;background:#0a84ff;color:#fff;border-radius:8px'>Send</button>
</form>
<script>
const TOKEN = {token!r};
const log = document.getElementById('log');
const f = document.getElementById('f');
const m = document.getElementById('m');
function append(who, text) {{
  const div = document.createElement('div');
  div.innerHTML = '<b>' + who + ':</b> ' + text.replace(/\\n/g,'<br>');
  div.style.margin = '6px 0';
  log.appendChild(div); log.scrollTop = log.scrollHeight;
}}
f.onsubmit = async (e) => {{
  e.preventDefault();
  const t = m.value.trim(); if (!t) return;
  m.value = ''; append('you', t);
  const r = await fetch('/chat', {{ method:'POST', headers:{{'Content-Type':'application/json','X-H5-Token':TOKEN}},
    body: JSON.stringify({{message:t}}) }});
  const j = await r.json();
  append('agent', j.output || JSON.stringify(j));
}};
</script></body></html>
""")
