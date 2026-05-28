"""FastAPI HTTP server.

Endpoints:
    GET  /health
    POST /chat                        — gated by auth
    POST /dev-team                    — gated by auth
    GET  /usage                       — usage summary (gated)
    GET  /sessions                    — list sessions (gated)
    POST /sessions                    — create session (gated)
    POST /sessions/{sid}/append       — append message (gated)
    GET  /sessions/{sid}              — list messages (gated)
    GET  /cron                        — list jobs (gated)
    POST /cron                        — add job (gated)
    DELETE /cron/{job_id}             — remove job (gated)

Auth:
    Set AGENTIC_ADMIN_KEY to enable auth. If unset, the server runs in
    'open' mode (suitable only for localhost dev). When set, every gated
    request must carry either:
        - X-Admin-Key:  <admin key>          (long-lived, full access)
        - X-H5-Token:   <one-time token>     (short-lived, full access)
    Tokens expire after 1800s by default and are stored in a TTL cache.

H5 access:
    POST /h5/token                    — issue one-time token (admin only)
    GET  /h5/page?token=...           — minimal HTML chat page
    The HTML client posts to /chat with X-H5-Token; the server validates.

Run:  uvicorn agentic_engine.server:app --port 9120
      (or:  agentic serve --port 9120)
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .core.agent import Agent
from .core.cron import CronManager
from .core.sessions import SessionStore
from .core.usage import default_tracker
from .teams import build_dev_team
from .tools import read_file, list_dir, grep_text, web_fetch


# ============= Token store (TTL + thread-safe) =============
class _TokenStore:
    def __init__(self) -> None:
        self._d: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self, ttl: int = 1800) -> str:
        tok = secrets.token_urlsafe(24)
        with self._lock:
            self._sweep_locked()
            self._d[tok] = time.time() + ttl
        return tok

    def check(self, tok: str) -> bool:
        with self._lock:
            self._sweep_locked()
            return tok in self._d

    def _sweep_locked(self) -> None:
        now = time.time()
        expired = [k for k, exp in self._d.items() if exp < now]
        for k in expired:
            self._d.pop(k, None)


_tokens = _TokenStore()
_store = SessionStore()
_cron = CronManager()


# ============= Lifespan: start/stop scheduler =============
@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        _cron.start()
    except Exception as e:  # apscheduler not installed → continue without cron
        print(f"[server] cron disabled: {e}")
    try:
        yield
    finally:
        try:
            _cron.stop()
        except Exception:
            pass


app = FastAPI(title="agentic-engine", version="0.2.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= Auth dependency =============
def require_auth(
    x_admin_key: str | None = Header(default=None),
    x_h5_token: str | None = Header(default=None),
) -> str:
    """Return 'admin' or 'h5' on success; 401 on failure.

    Open-mode (no AGENTIC_ADMIN_KEY env) returns 'open' for everyone — useful
    for local dev. As soon as you set AGENTIC_ADMIN_KEY, all gated routes
    require a header.
    """
    expected = os.getenv("AGENTIC_ADMIN_KEY", "")
    if not expected:
        return "open"
    if x_admin_key and secrets.compare_digest(x_admin_key, expected):
        return "admin"
    if x_h5_token and _tokens.check(x_h5_token):
        return "h5"
    raise HTTPException(status_code=401, detail="auth required")


def require_admin(x_admin_key: str | None = Header(default=None)) -> str:
    expected = os.getenv("AGENTIC_ADMIN_KEY", "")
    if not expected:
        raise HTTPException(status_code=401, detail="AGENTIC_ADMIN_KEY not configured")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="bad admin key")
    return "admin"


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


# ============= Health (open) =============
@app.get("/health")
def health() -> dict:
    auth_required = bool(os.getenv("AGENTIC_ADMIN_KEY", ""))
    return {"ok": True, "version": "0.2.0", "auth_required": auth_required}


# ============= Chat / dev-team =============
@app.post("/chat")
def chat(req: ChatReq, _: str = Depends(require_auth)) -> dict:
    a = Agent(
        name="api-solo",
        role=req.role,
        tools=[read_file, list_dir, grep_text, web_fetch],
        model=req.model,
    )
    res = a.run(req.message, verbose=False)
    if req.session_id:
        try:
            _store.append(req.session_id, "user", req.message)
            _store.append(req.session_id, "assistant", res.output)
        except Exception as e:
            return {"output": res.output, "turns": res.turns, "tool_calls": res.tool_calls,
                    "warning": f"session persist failed: {e}"}
    return {"output": res.output, "turns": res.turns, "tool_calls": res.tool_calls}


@app.post("/dev-team")
def dev_team(req: DevTeamReq, _: str = Depends(require_auth)) -> dict:
    team = build_dev_team(model=req.model)
    results = team.run_sequential(req.goal, verbose=False)
    return {"results": [{"agent": r.agent, "output": r.output, "turns": r.turns} for r in results]}


# ============= Usage =============
@app.get("/usage")
def usage(days: int | None = None, _: str = Depends(require_auth)) -> dict:
    return default_tracker().summary(days=days)


# ============= Sessions =============
@app.get("/sessions")
def list_sessions(project_id: str | None = None, _: str = Depends(require_auth)) -> dict:
    items = _store.list_sessions(project_id=project_id)
    return {"sessions": [s.__dict__ for s in items]}


@app.post("/sessions")
def create_session(req: SessionCreateReq, _: str = Depends(require_auth)) -> dict:
    proj = _store.upsert_project(req.project_name, req.project_root)
    s = _store.new_session(proj.id, req.title)
    return {"project": proj.__dict__, "session": s.__dict__}


@app.post("/sessions/{sid}/append")
def session_append(sid: str, req: AppendReq, _: str = Depends(require_auth)) -> dict:
    try:
        m = _store.append(sid, req.role, req.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": m.__dict__}


@app.get("/sessions/{sid}")
def session_history(sid: str, _: str = Depends(require_auth)) -> dict:
    msgs = _store.history(sid)
    return {"messages": [m.__dict__ for m in msgs]}


# ============= Cron =============
@app.get("/cron")
def cron_list(_: str = Depends(require_auth)) -> dict:
    return {"jobs": [j.__dict__ for j in _cron.list()]}


@app.post("/cron")
def cron_add(req: CronAddReq, _: str = Depends(require_auth)) -> dict:
    try:
        job = _cron.add(req.name, req.schedule, req.payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid job: {e}")
    return {"job": job.__dict__}


@app.delete("/cron/{job_id}")
def cron_remove(job_id: str, _: str = Depends(require_auth)) -> dict:
    ok = _cron.remove(job_id)
    return {"removed": ok}


# ============= H5 =============
@app.post("/h5/token")
def h5_issue_token(_: str = Depends(require_admin), ttl: int = 1800) -> dict:
    tok = _tokens.issue(ttl=ttl)
    return {"token": tok, "ttl": ttl}


@app.get("/h5/page", response_class=HTMLResponse)
def h5_page(token: str) -> str:
    if not _tokens.check(token):
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
function escapeHtml(s) {{ return (s||'').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c])); }}
function append(who, text) {{
  const div = document.createElement('div');
  div.innerHTML = '<b>' + who + ':</b> ' + escapeHtml(text).replace(/\\n/g,'<br>');
  div.style.margin = '6px 0';
  log.appendChild(div); log.scrollTop = log.scrollHeight;
}}
f.onsubmit = async (e) => {{
  e.preventDefault();
  const t = m.value.trim(); if (!t) return;
  m.value = ''; append('you', t);
  const r = await fetch('/chat', {{ method:'POST',
    headers:{{'Content-Type':'application/json','X-H5-Token':TOKEN}},
    body: JSON.stringify({{message:t}}) }});
  const j = await r.json();
  append('agent', j.output || JSON.stringify(j));
}};
</script></body></html>
""")
