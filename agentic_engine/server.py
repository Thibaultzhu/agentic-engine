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
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from . import ratelimit
from .core.agent import Agent
from .core.auth import Role, User, user_from_token
from .core.cron import CronManager
from .core.sessions import SessionStore
from .core.usage import default_tracker
from .logging import configure as configure_logging
from .teams import build_dev_team
from .telemetry import setup_tracing, span
from .tools import grep_text, list_dir, read_file, web_fetch


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


# ============= Background job store =============
class _JobStore:
    def __init__(self) -> None:
        self._d: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        jid = secrets.token_urlsafe(8)
        with self._lock:
            self._d[jid] = {"id": jid, "status": "queued", "result": None, "error": None,
                            "created_at": time.time()}
        return jid

    def set_done(self, jid: str, result: Any) -> None:
        with self._lock:
            if jid in self._d:
                self._d[jid]["status"] = "done"
                self._d[jid]["result"] = result
                self._d[jid]["finished_at"] = time.time()

    def set_error(self, jid: str, err: str) -> None:
        with self._lock:
            if jid in self._d:
                self._d[jid]["status"] = "error"
                self._d[jid]["error"] = err
                self._d[jid]["finished_at"] = time.time()

    def get(self, jid: str) -> dict | None:
        with self._lock:
            return dict(self._d.get(jid)) if jid in self._d else None


_jobs = _JobStore()


# ============= Lifespan: start/stop scheduler =============
@asynccontextmanager
async def _lifespan(app: FastAPI):
    configure_logging()
    setup_tracing("agentic-engine")
    try:
        _cron.start()
    except Exception as e:  # apscheduler not installed → continue without cron
        print(f"[server] cron disabled: {e}")
    try:
        yield
    finally:
        with suppress(Exception):
            _cron.stop()


app = FastAPI(title="agentic-engine", version="0.3.0", lifespan=_lifespan)
ratelimit.apply(app)
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
    authorization: str | None = Header(default=None),
) -> str:
    """Return 'admin' / 'h5' / 'jwt:<sub>:<role>' / 'open' on success.

    Open-mode (no AGENTIC_ADMIN_KEY env, no AGENTIC_JWT_SECRET) returns
    ``'open'``. As soon as either is set, gated routes require:
        * ``X-Admin-Key`` header (long-lived, full access)
        * ``X-H5-Token`` header (short-lived, full access)
        * ``Authorization: Bearer <jwt>`` (when AGENTIC_JWT_SECRET set)
    """
    expected = os.getenv("AGENTIC_ADMIN_KEY", "")
    jwt_secret = os.getenv("AGENTIC_JWT_SECRET", "")
    if not expected and not jwt_secret:
        return "open"
    if expected and x_admin_key and secrets.compare_digest(x_admin_key, expected):
        return "admin"
    if x_h5_token and _tokens.check(x_h5_token):
        return "h5"
    if jwt_secret and authorization and authorization.lower().startswith("bearer "):
        try:
            u = user_from_token(authorization.split(None, 1)[1].strip())
            return f"jwt:{u.id}:{u.role.value}"
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=401, detail=f"jwt: {e}") from e
    raise HTTPException(status_code=401, detail="auth required")


def require_role(min_role: Role) -> Any:
    """Dependency factory that requires at least ``min_role`` from JWT.

    Falls through to allow ``admin``/``open``/``h5`` (treated as admin-equiv)
    so the existing v0.2 callers keep working.
    """
    def _dep(_: str = Depends(require_auth),
             authorization: str | None = Header(default=None)) -> User:
        if not (authorization and authorization.lower().startswith("bearer ")):
            return User(id="admin", role=Role.ADMIN)
        u = user_from_token(authorization.split(None, 1)[1].strip())
        if not u.has(min_role):
            raise HTTPException(status_code=403, detail=f"role {u.role} < {min_role}")
        return u

    return _dep


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
    auth_required = bool(os.getenv("AGENTIC_ADMIN_KEY", "")) or bool(os.getenv("AGENTIC_JWT_SECRET", ""))
    return {"ok": True, "version": "0.3.0", "auth_required": auth_required}


# ============= Chat / dev-team =============
@app.post("/chat")
def chat(req: ChatReq, _: str = Depends(require_auth)) -> dict:
    with span("chat", role=req.role, model=req.model or ""):
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


# ============= SSE streaming =============
@app.post("/chat/stream")
def chat_stream_endpoint(req: ChatReq, _: str = Depends(require_auth)) -> StreamingResponse:
    """Server-Sent-Events streaming. Returns ``text/event-stream`` of deltas.

    Each event has the line ``data: <chunk>`` (newlines escaped). The stream
    terminates with ``data: [DONE]``.
    """
    a = Agent(
        name="api-stream",
        role=req.role,
        tools=[],
        model=req.model,
    )

    def _gen() -> Any:
        try:
            for piece in a.run_stream(req.message):
                # SSE: each line has to be `data: <json>` with terminating blank line.
                yield f"data: {piece.replace(chr(10), chr(92) + 'n')}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: [ERROR] {type(e).__name__}: {e}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


# ============= WebSocket streaming =============
@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    """Bidirectional chat over WebSocket — newline-delimited JSON frames.

    Auth: pass ``?token=<jwt>`` or ``?admin_key=<key>`` query params (browsers
    don't let you set arbitrary headers on WebSocket handshake).
    """
    await ws.accept()
    expected = os.getenv("AGENTIC_ADMIN_KEY", "")
    jwt_secret = os.getenv("AGENTIC_JWT_SECRET", "")
    qs_token = ws.query_params.get("token", "")
    qs_admin = ws.query_params.get("admin_key", "")
    authed = (
        (not expected and not jwt_secret)  # open-mode
        or (expected and qs_admin and secrets.compare_digest(qs_admin, expected))
        or (jwt_secret and qs_token and _check_jwt_silent(qs_token))
    )
    if not authed:
        await ws.close(code=4401)
        return
    try:
        while True:
            data = await ws.receive_json()
            msg = data.get("message", "")
            if not isinstance(msg, str) or not msg.strip():
                await ws.send_json({"type": "error", "error": "empty message"})
                continue
            a = Agent(name="ws", role="general-purpose", tools=[], model=data.get("model"))
            try:
                async for piece in a.run_stream_async(msg):
                    await ws.send_json({"type": "delta", "content": piece})
                await ws.send_json({"type": "done"})
            except Exception as e:  # noqa: BLE001
                await ws.send_json({"type": "error", "error": str(e)})
    except WebSocketDisconnect:
        return


def _check_jwt_silent(token: str) -> bool:
    try:
        user_from_token(token)
        return True
    except Exception:
        return False


@app.post("/dev-team")
def dev_team(
    req: DevTeamReq,
    background: BackgroundTasks,
    async_: bool = False,
    _: str = Depends(require_auth),
) -> dict:
    """Run the 5-role dev team.

    Default is synchronous (blocks). Set ?async_=true to enqueue and get a job id;
    poll GET /jobs/{job_id} for status/result. The synchronous mode is kept for
    backwards compat but will block uvicorn for the duration of the run.
    """
    if not async_:
        team = build_dev_team(model=req.model)
        results = team.run_sequential(req.goal, verbose=False)
        return {"results": [{"agent": r.agent, "output": r.output, "turns": r.turns} for r in results]}

    job_id = _jobs.create()

    def _run() -> None:
        try:
            team = build_dev_team(model=req.model)
            results = team.run_sequential(req.goal, verbose=False)
            _jobs.set_done(job_id, {"results": [
                {"agent": r.agent, "output": r.output, "turns": r.turns} for r in results
            ]})
        except Exception as e:  # noqa: BLE001
            _jobs.set_error(job_id, str(e))

    background.add_task(_run)
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str, _: str = Depends(require_auth)) -> dict:
    j = _jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return j


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
        raise HTTPException(status_code=400, detail=str(e)) from e
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
        raise HTTPException(status_code=400, detail=f"invalid job: {e}") from e
    return {"job": job.__dict__}


@app.delete("/cron/{job_id}")
def cron_remove(job_id: str, _: str = Depends(require_auth)) -> dict:
    ok = _cron.remove(job_id)
    return {"removed": ok}


@app.get("/cron/{job_id}/runs")
def cron_runs(job_id: str, _: str = Depends(require_auth)) -> dict:
    return {"runs": [r.__dict__ for r in _cron.runs(job_id)]}


@app.post("/cron/{job_id}/enable")
def cron_enable_ep(job_id: str, _: str = Depends(require_auth)) -> dict:
    try:
        changed = _cron.enable(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"changed": changed}


@app.post("/cron/{job_id}/disable")
def cron_disable_ep(job_id: str, _: str = Depends(require_auth)) -> dict:
    try:
        changed = _cron.disable(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"changed": changed}


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


# ============= JWT auth =============
class TokenIssueReq(BaseModel):
    sub: str
    role: str = "user"
    expires_in: int = 3600


@app.post("/auth/token")
def issue_jwt(req: TokenIssueReq, _: str = Depends(require_admin)) -> dict:
    """Issue an HS256 JWT (requires admin key + AGENTIC_JWT_SECRET)."""
    from .core.auth import make_jwt

    try:
        Role(req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"unknown role: {req.role}") from e
    token = make_jwt({"sub": req.sub, "role": req.role}, expires_in=req.expires_in)
    return {"token": token, "expires_in": req.expires_in}


@app.get("/me")
def me(authorization: str | None = Header(default=None)) -> dict:
    """Inspect current bearer token (no admin/h5 fallback)."""
    if not (authorization and authorization.lower().startswith("bearer ")):
        raise HTTPException(status_code=401, detail="bearer token required")
    try:
        u = user_from_token(authorization.split(None, 1)[1].strip())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=str(e)) from e
    return {"id": u.id, "role": u.role.value, "extra": u.extra or {}}


# ============= Eval =============
class EvalReq(BaseModel):
    tasks: list[dict[str, Any]]


@app.post("/eval")
def run_eval_endpoint(req: EvalReq, _: str = Depends(require_auth)) -> dict:
    from .evals import Task, run_eval

    tasks = [Task.from_dict(d) for d in req.tasks]

    def runner(prompt: str) -> str:
        a = Agent(name="eval", role="evaluator", tools=[], model=None)
        return a.run(prompt, verbose=False).output

    report = run_eval(tasks, runner=runner)
    return report.to_dict()
