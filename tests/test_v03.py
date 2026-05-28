"""Tests for v0.3.0 additions: auth/JWT, RAG, permissions glob, pricing,
cron retry/DLQ, async agent surface, ratelimit bypass, structured logging,
telemetry no-op, plugins loader, evals harness, server /auth/token + /me.
"""
from __future__ import annotations

import pytest

# ---------- auth / JWT ----------

def test_jwt_roundtrip(monkeypatch):
    monkeypatch.setenv("AGENTIC_JWT_SECRET", "test-secret-32-bytes-min-padding-x")
    from agentic_engine.core.auth import Role, make_jwt, user_from_token, verify_jwt
    tok = make_jwt({"sub": "alice", "role": Role.ADMIN.value}, expires_in=60)
    claims = verify_jwt(tok)
    assert claims["sub"] == "alice"
    assert claims["role"] == "admin"
    u = user_from_token(tok)
    assert u.id == "alice"
    assert u.role == Role.ADMIN


def test_jwt_rejects_tampered_signature(monkeypatch):
    monkeypatch.setenv("AGENTIC_JWT_SECRET", "test-secret-32-bytes-min-padding-x")
    from agentic_engine.core.auth import make_jwt, verify_jwt
    tok = make_jwt({"sub": "u"})
    bad = tok[:-2] + ("AA" if tok[-2:] != "AA" else "BB")
    with pytest.raises(Exception):
        verify_jwt(bad)


# ---------- RAG (BM25 fallback) ----------

def test_rag_bm25_fallback_basic(tmp_path):
    from agentic_engine.core.rag import RAGMemory
    rag = RAGMemory(persist_dir=None)
    rag.add("the quick brown fox jumps over the lazy dog", {"k": "a"})
    rag.add("hello world from agentic engine", {"k": "b"})
    rag.add("fastapi server with websockets and sse", {"k": "c"})
    hits = rag.search("fox lazy dog", top_k=2)
    assert hits, "BM25 returned no hits"
    assert "fox" in hits[0][0]


# ---------- permissions: glob + JSON persistence ----------

def test_permissions_glob_match_and_persist(tmp_path):
    import json

    from agentic_engine.core.permissions import PermissionPolicy, Rule
    pol = PermissionPolicy(rules=[
        Rule(tool="bash_run", decision="deny", args={"command": "rm *"}),
        Rule(tool="web_fetch", decision="allow", args={"url": "https://example.com/*"}),
    ])
    assert pol.decide("bash_run", {"command": "rm tmp"}) == "deny"
    assert pol.decide("web_fetch", {"url": "https://example.com/x.html"}) == "allow"
    assert pol.decide("bash_run", {"command": "echo hi"}) == "ask"

    # round-trip via JSON
    out = tmp_path / "perms.json"
    out.write_text(json.dumps(pol.to_dict()))
    again = PermissionPolicy.from_file(out)
    assert again.decide("bash_run", {"command": "rm tmp"}) == "deny"


# ---------- pricing multi-region + FX ----------

def test_pricing_estimate_regions():
    from agentic_engine.core.pricing import estimate
    cn = estimate("qwen-plus", prompt_tokens=1_000_000, completion_tokens=1_000_000, region="cn")
    sg = estimate("qwen-plus", prompt_tokens=1_000_000, completion_tokens=1_000_000, region="sg")
    assert cn["currency"] == "CNY"
    assert sg["currency"] in ("USD", "CNY")
    assert cn["cost"] >= 0
    assert sg["cost"] >= 0


def test_pricing_currency_conversion():
    from agentic_engine.core.pricing import convert
    # 100 CNY -> USD -> CNY should round-trip approximately
    usd = convert(100.0, "CNY", "USD")
    back = convert(usd, "USD", "CNY")
    assert abs(back - 100.0) < 0.5


# ---------- cron retry + DLQ ----------

def test_cron_retry_and_dlq(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    import agentic_engine.config as cfg
    from agentic_engine.config import Settings
    cfg._settings = Settings.load()

    from agentic_engine.core.cron import CronJob, CronManager

    calls = {"n": 0}

    def runner(payload):
        calls["n"] += 1
        raise RuntimeError("boom")

    mgr = CronManager(runner=runner)
    job = CronJob(
        id="j1", name="t",
        schedule={"kind": "every", "every_seconds": 60},
        payload={"type": "agent_turn", "message": "x"},
        max_retries=2, retry_backoff_s=0,
    )
    mgr._invoke_with_retry(job)
    assert calls["n"] == 3
    dlq = tmp_path / "cron.dlq.jsonl"
    assert dlq.exists() and dlq.read_text().strip()


# ---------- async agent surface ----------

@pytest.mark.asyncio
async def test_run_async_dispatches_to_run(monkeypatch):
    from agentic_engine.core.agent import Agent, AgentResult

    a = Agent(name="t", role="tester")
    monkeypatch.setattr(
        Agent, "run",
        lambda self, user_input, verbose=False: AgentResult(agent="t", output="ok"),
    )
    out = await a.run_async("hi")
    assert out.output == "ok"


# ---------- ratelimit bypass ----------

def test_ratelimit_disabled_via_env(monkeypatch):
    monkeypatch.setenv("AGENTIC_RATELIMIT_DISABLE", "1")
    from agentic_engine import ratelimit

    class _StubApp:
        state = type("S", (), {})()
        exception_handlers = {}
        def add_exception_handler(self, *a, **k): pass
        def add_middleware(self, *a, **k): pass
    ratelimit.apply(_StubApp())  # must not raise


# ---------- structured logging ----------

def test_logging_get_logger_works():
    from agentic_engine.logging import get_logger
    log = get_logger("test")
    bound = log.bind(component="x") if hasattr(log, "bind") else log
    bound.info("hello world")  # no kwargs into stdlib log()


# ---------- telemetry no-op ----------

def test_telemetry_span_noop_without_otel(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_ENABLE", raising=False)
    from agentic_engine.telemetry import setup_tracing, span
    setup_tracing("test")
    with span("op", k="v"):
        pass


# ---------- plugins loader ----------

def test_plugins_load_does_not_crash():
    from agentic_engine.plugins import load_plugins
    plugins = load_plugins()
    assert hasattr(plugins, "__iter__")


# ---------- evals harness (regex + contains) ----------

def test_evals_judge_regex_and_contains():
    from agentic_engine.evals import _judge

    ok_regex, _ = _judge("hello   world!", {"kind": "regex", "value": r"hello\s+world"}, "")
    assert ok_regex is True

    ok_contains, _ = _judge("agentic engine", {"kind": "contains", "value": "ENGINE"}, "")
    assert ok_contains is True

    bad, _ = _judge("nope", {"kind": "contains", "value": "ENGINE"}, "")
    assert bad is False


def test_evals_run_eval_with_runner():
    from agentic_engine.evals import Task, run_eval

    tasks = [
        Task(name="echo-greet", input="hello", expect={"kind": "contains", "value": "HI"}),
        Task(name="echo-bye",   input="bye",   expect={"kind": "contains", "value": "see you"}),
    ]
    rep = run_eval(tasks, runner=lambda x: f"hi back: {x}")
    assert rep.results[0].passed is True
    assert rep.results[1].passed is False
    assert 0 < rep.pass_rate < 1


# ---------- server /auth/token + /me ----------

def test_server_health_and_auth_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    monkeypatch.setenv("AGENTIC_JWT_SECRET", "test-secret-32-bytes-min-padding-x")
    monkeypatch.setenv("AGENTIC_ADMIN_KEY", "k1")
    monkeypatch.setenv("AGENTIC_RATELIMIT_DISABLE", "1")
    import agentic_engine.config as cfg
    from agentic_engine.config import Settings
    cfg._settings = Settings.load()

    from fastapi.testclient import TestClient

    from agentic_engine.server import app
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("version") == "0.3.0"

    r = c.post(
        "/auth/token",
        json={"sub": "bob", "role": "user", "expires_in": 60},
        headers={"X-Admin-Key": "k1"},
    )
    assert r.status_code == 200, r.text
    tok = r.json()["token"]

    r = c.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["id"] == "bob"

    # /me without bearer must reject
    r = c.get("/me")
    assert r.status_code == 401
