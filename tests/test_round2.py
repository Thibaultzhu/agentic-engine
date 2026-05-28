"""Tests for the round-2 improvements (P1 remainder + all P2)."""
from __future__ import annotations

import json
import threading
import time
from typing import Annotated

import pytest


# ---------- Tool typing: Optional / list / Annotated / docstring ----------
def test_tool_typing_supports_optional_list_annotated_and_docstrings():
    from agentic_engine.core.tool import tool

    @tool(name="typed_demo")
    def fn(
        title: str,
        tags: list[str],
        opt: int | None = None,
        verbose: Annotated[bool, "Whether to print debug info"] = False,
    ) -> str:
        """Demo tool.

        Args:
            title: The title to display.
            tags: List of tags.
            opt: Optional integer.
        """
        return "ok"

    schema = fn.parameters
    props = schema["properties"]
    assert props["title"]["type"] == "string"
    assert props["tags"] == {"type": "array", "items": {"type": "string"},
                              "description": "List of tags."}
    # Optional[int] resolves to int (not required), opt is not in required[]
    assert props["opt"]["type"] == "integer"
    assert "opt" not in schema["required"]
    # Annotated description wins over docstring
    assert props["verbose"]["description"] == "Whether to print debug info"
    assert "title" in schema["required"] and "tags" in schema["required"]
    assert fn.description == "Demo tool."  # docstring summary line


def test_tool_typing_dict_value_type():
    from agentic_engine.core.tool import tool

    @tool(name="dict_demo")
    def fn(env: dict[str, int]) -> str:
        return ""

    p = fn.parameters["properties"]["env"]
    assert p["type"] == "object"
    assert p["additionalProperties"] == {"type": "integer"}


# ---------- Orchestrator dispatch JSON extractor ----------
def test_dispatch_json_extracts_from_fence_and_prose():
    from agentic_engine.core.orchestrator import _extract_json_object

    s1 = '```json\n{"alice": "do A", "bob": "do B"}\n```'
    assert _extract_json_object(s1) == {"alice": "do A", "bob": "do B"}

    s2 = 'Sure, here is the plan:\n{"alice": "do A"}\nLet me know if that works.'
    assert _extract_json_object(s2) == {"alice": "do A"}

    s3 = 'No JSON here at all.'
    assert _extract_json_object(s3) is None

    # Nested braces (string contains "}") must not break the extractor.
    s4 = 'Plan: {"alice": "say {hi} to bob", "bob": "ok"} done.'
    out = _extract_json_object(s4)
    assert out == {"alice": "say {hi} to bob", "bob": "ok"}


# ---------- Memory bootstrap cap ----------
def test_memory_bootstrap_caps_per_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    from agentic_engine.core.memory import Memory
    m = Memory()
    big = "x" * 5000
    m.add("user", big)
    block = m.bootstrap_block(max_chars_per_scope=500)
    # The user scope alone should be capped well under 5000 chars
    user_section = block.split("\n\n")[0]
    assert len(user_section) < 700
    assert "elided" in user_section


# ---------- Sessions hard delete ----------
def test_sessions_delete_session_and_project(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    from agentic_engine.core.sessions import SessionStore
    store = SessionStore()
    p = store.upsert_project("demo", ".")
    s = store.new_session(p.id, "t")
    store.append(s.id, "user", "hi")
    store.append(s.id, "assistant", "yo")

    n = store.delete_session(s.id)
    assert n == 2
    assert store.list_sessions(p.id) == []
    with pytest.raises(KeyError):
        store.delete_session(s.id)

    # Now project delete cascade
    s2 = store.new_session(p.id, "t2")
    store.append(s2.id, "user", "x")
    sessions, msgs = store.delete_project(p.id)
    assert sessions == 1 and msgs == 1
    assert all(pp.id != p.id for pp in store.list_projects())


# ---------- Cron enable/disable ----------
def test_cron_enable_disable(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    from agentic_engine.core.cron import CronManager
    mgr = CronManager()
    job = mgr.add("daily", {"kind": "cron", "expr": "0 9 * * *"},
                  {"type": "agent_turn", "message": "x"})
    assert job.enabled is True
    assert mgr.disable(job.id) is True
    assert mgr.disable(job.id) is False  # already disabled
    # Persisted across reload
    again = CronManager()
    assert next(j for j in again.list() if j.id == job.id).enabled is False
    assert again.enable(job.id) is True


# ---------- pricing.json override ----------
def test_pricing_override_via_json(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    (tmp_path / "pricing.json").write_text(
        json.dumps({"my-model": [10.0, 30.0]}), encoding="utf-8"
    )
    from agentic_engine.core.usage import estimate_cost
    # 1M input + 1M output = 10 + 30 CNY
    assert abs(estimate_cost("my-model", 1_000_000, 1_000_000) - 40.0) < 1e-6


# ---------- MCP schema sanitizer ----------
def test_mcp_schema_sanitizer_strips_unknown_keys():
    from agentic_engine.core.mcp import _sanitize_schema
    inp = {
        "type": "object",
        "properties": {"x": {"type": "string", "$comment": "junk", "format": "weird"}},
        "required": ["x"],
        "additionalProperties": False,   # not in the OpenAI-supported set
        "$schema": "http://x",
    }
    out = _sanitize_schema(inp)
    assert "$schema" not in out
    assert "additionalProperties" not in out
    assert out["properties"]["x"] == {"type": "string"}


# ---------- write_file safety ----------
def test_write_file_if_exists_fail_and_backup(tmp_path):
    from agentic_engine.tools import write_file

    target = tmp_path / "a.txt"
    write_file(path=str(target), content="v1")
    assert target.read_text() == "v1"

    # if_exists='fail' refuses to overwrite
    out = write_file(path=str(target), content="v2", if_exists="fail")
    assert out.startswith("[refused]")
    assert target.read_text() == "v1"

    # backup creates .bak
    out = write_file(path=str(target), content="v2", backup=True)
    assert "(.bak created)" in out
    assert target.read_text() == "v2"
    assert (tmp_path / "a.txt.bak").read_text() == "v1"

    # append mode
    write_file(path=str(target), content=" + extra", if_exists="append")
    assert target.read_text() == "v2 + extra"


# ---------- grep ignore defaults ----------
def test_grep_ignores_common_dirs_by_default(tmp_path):
    from agentic_engine.tools import grep_text

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("token MARKER\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "trash.js").write_text("MARKER\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "stuff").write_text("MARKER\n")

    out = grep_text(pattern="MARKER", path=str(tmp_path))
    assert "main.py" in out
    assert "node_modules" not in out
    assert ".git" not in out


# ---------- git diff non-repo ----------
def test_git_diff_friendly_error_for_non_repo(tmp_path):
    from agentic_engine.tools import git_diff
    out = git_diff(repo=str(tmp_path))
    assert "not a git repository" in out


# ---------- web_fetch SSRF ----------
def test_web_fetch_blocks_loopback_and_link_local():
    from agentic_engine.tools.web import _ssrf_check
    assert _ssrf_check("http://127.0.0.1/") is not None
    assert _ssrf_check("http://localhost:8080/") is not None
    assert _ssrf_check("http://169.254.169.254/latest/meta-data/") is not None
    assert _ssrf_check("http://metadata.google.internal/") is not None
    assert _ssrf_check("ftp://example.com/") is not None
    # Public host should pass (best-effort DNS dependent — skip if no DNS).
    try:
        ok = _ssrf_check("https://www.example.com/")
    except Exception:
        pytest.skip("no DNS")
    assert ok is None


# ---------- Telegram backoff escalates 401 ----------
def test_telegram_listen_raises_on_401(monkeypatch):
    from agentic_engine.adapters.telegram import TelegramAdapter, TelegramFatalError

    class _Resp:
        status_code = 401
        text = '{"description":"Unauthorized"}'

        def json(self) -> dict:
            return {"description": "Unauthorized"}

    def fake_get(*a, **kw):
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    a = TelegramAdapter(token="xxx", max_consecutive_failures=2)
    with pytest.raises(TelegramFatalError):
        a.listen(lambda m: None)


# ---------- Telegram backoff retries on 500 then escalates ----------
def test_telegram_listen_escalates_after_too_many_5xx(monkeypatch):
    from agentic_engine.adapters.telegram import TelegramAdapter, TelegramFatalError

    class _Resp:
        status_code = 502
        text = "bad gateway"

        def json(self) -> dict:
            return {}

    def fake_get(*a, **kw):
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    a = TelegramAdapter(token="xxx", max_consecutive_failures=2,
                        base_backoff=0.001, max_backoff=0.001)
    with pytest.raises(TelegramFatalError):
        a.listen(lambda m: None)


# ---------- Agent retry on transient ----------
def test_agent_retries_transient_error(monkeypatch):
    from agentic_engine.core import agent as agent_mod

    calls = {"n": 0}

    class _Msg:
        content = "hello"
        tool_calls = None

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = None

    def flaky_chat(messages, agent_name=None, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("rate limit reached, please retry")
        return _Resp()

    monkeypatch.setattr(agent_mod, "chat", flaky_chat)
    a = agent_mod.Agent(name="t", transient_retries=3)
    # Make backoff effectively instant.
    monkeypatch.setattr(agent_mod.time, "sleep", lambda *_: None)
    res = a.run("hi", verbose=False)
    assert res.output == "hello"
    assert calls["n"] == 3


# ---------- Agent history sliding window ----------
def test_agent_compact_keeps_system_and_recent():
    from agentic_engine.core.agent import Agent
    a = Agent(name="t", history_window=4)
    msgs = [{"role": "system", "content": "S"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    out = a._compact(msgs)
    # head system + 4 tail
    assert out[0]["role"] == "system"
    assert len(out) <= 1 + 4 + 2  # +2 leeway for tool_calls/tool repair
    assert out[-1] == msgs[-1]


# ---------- Tool result truncation ----------
def test_agent_truncates_huge_tool_results(monkeypatch):
    from agentic_engine.core import agent as agent_mod
    from agentic_engine.core.tool import Tool

    big = "y" * 50_000

    def big_handler() -> str:
        return big

    big_tool = Tool(name="bigt", description="huge",
                    handler=big_handler, parameters={"type": "object",
                                                     "properties": {}, "required": []})

    state = {"i": 0}

    class _ToolCallFn:
        name = "bigt"
        arguments = "{}"

    class _ToolCall:
        id = "c1"
        function = _ToolCallFn()

    class _Msg1:
        content = ""
        tool_calls = [_ToolCall()]

    class _Msg2:
        content = "done"
        tool_calls = None

    class _R1:
        choices = [type("C", (), {"message": _Msg1()})()]
        usage = None

    class _R2:
        choices = [type("C", (), {"message": _Msg2()})()]
        usage = None

    def fake_chat(messages, **kw):
        state["i"] += 1
        return _R1() if state["i"] == 1 else _R2()

    monkeypatch.setattr(agent_mod, "chat", fake_chat)

    a = agent_mod.Agent(name="t", tools=[big_tool], tool_result_max_chars=500,
                         transient_retries=0)
    res = a.run("go", verbose=False)
    # Find the tool message and check length
    tool_msgs = [m for m in res.raw_messages if m.get("role") == "tool"]
    assert tool_msgs and "truncated" in tool_msgs[0]["content"]
    assert len(tool_msgs[0]["content"]) <= 600


# ---------- Server: dev-team async + jobs polling ----------
def test_server_devteam_async_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    monkeypatch.delenv("AGENTIC_ADMIN_KEY", raising=False)
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    import importlib
    import agentic_engine.server as srv
    importlib.reload(srv)

    # Patch build_dev_team to a one-step team that just returns immediately.
    class _Res:
        agent = "alice"
        output = "hello"
        turns = 1

    class _Team:
        def run_sequential(self, goal, verbose=False):
            return [_Res()]

    monkeypatch.setattr(srv, "build_dev_team", lambda model=None: _Team())

    from fastapi.testclient import TestClient
    client = TestClient(srv.app)

    r = client.post("/dev-team?async_=true", json={"goal": "x"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    # Poll a few times until done
    for _ in range(20):
        r = client.get(f"/jobs/{job_id}")
        assert r.status_code == 200
        if r.json()["status"] == "done":
            break
        time.sleep(0.05)
    else:
        pytest.fail("job never completed")

    body = r.json()
    assert body["status"] == "done"
    assert body["result"]["results"][0]["output"] == "hello"


# ---------- Server: cron enable/disable endpoints ----------
def test_server_cron_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    monkeypatch.delenv("AGENTIC_ADMIN_KEY", raising=False)
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    import importlib
    import agentic_engine.server as srv
    importlib.reload(srv)

    from fastapi.testclient import TestClient
    client = TestClient(srv.app)

    r = client.post("/cron", json={
        "name": "demo",
        "schedule": {"kind": "cron", "expr": "0 9 * * *"},
        "payload": {"type": "agent_turn", "message": "x"},
    })
    assert r.status_code == 200
    jid = r.json()["job"]["id"]

    r = client.post(f"/cron/{jid}/disable")
    assert r.status_code == 200 and r.json()["changed"] is True
    r = client.post(f"/cron/{jid}/enable")
    assert r.status_code == 200 and r.json()["changed"] is True
    r = client.post("/cron/nope/disable")
    assert r.status_code == 404


# ---------- Adapters: split & re-exports ----------
def test_imadapter_split_and_reexports():
    from agentic_engine.adapters import IMSender, IMReceiver, IMAdapter
    assert issubclass(IMAdapter, IMSender)
    assert issubclass(IMAdapter, IMReceiver)


def test_top_level_reexports_ops():
    import agentic_engine as ae
    assert ae.SessionStore is not None
    assert ae.CronManager is not None
    assert ae.UsageTracker is not None
    assert ae.MCPClient is not None
    assert ae.add_worktree is not None


# ---------- LLM via respx mock ----------
def test_llm_chat_via_respx(monkeypatch):
    pytest.importorskip("respx")
    import respx
    import httpx as _httpx
    from openai import OpenAI

    fake = {
        "id": "x", "object": "chat.completion", "created": 1, "model": "qwen-plus",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    with respx.mock(base_url="https://dashscope.aliyuncs.com") as router:
        router.post("/compatible-mode/v1/chat/completions").mock(
            return_value=_httpx.Response(200, json=fake)
        )
        client = OpenAI(api_key="sk-x", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert resp.choices[0].message.content == "hi"
