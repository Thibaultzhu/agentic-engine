"""Regression tests for the post-review fixes."""
import os
import time

import pytest


# ---------- bash blacklist ----------
def test_bash_blocks_obvious_destructive():
    from agentic_engine.tools import bash_run

    bad = [
        "rm -rf /",
        "rm -rf  /",          # extra space
        "rm -rf ~",
        "rm -rf $HOME",
        "/bin/rm -rf /",
        "mkfs.ext4 /dev/sda1",
        ":(){ :|:& };:",
        "shutdown -h now",
        "dd if=/dev/zero of=/dev/sda",
    ]
    for cmd in bad:
        out = bash_run(command=cmd)
        assert out.startswith("[refused]"), f"NOT refused: {cmd} → {out}"


def test_bash_allows_safe_commands(tmp_path):
    from agentic_engine.tools import bash_run
    out = bash_run(command="echo hi", cwd=str(tmp_path))
    assert "hi" in out


# ---------- sqlite FK ----------
def test_sessions_foreign_key_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    from agentic_engine.core.sessions import SessionStore
    store = SessionStore()
    with pytest.raises(Exception):
        store.append("does-not-exist", "user", "hi")


# ---------- cron eager validation ----------
def test_cron_rejects_bad_expression(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    from agentic_engine.core.cron import CronManager
    mgr = CronManager()
    with pytest.raises(Exception):
        mgr.add("bad", {"kind": "cron", "expr": "this is not cron"}, {"type": "agent_turn", "message": "x"})
    # Bad job must not be persisted.
    assert all(j.name != "bad" for j in CronManager().list())


# ---------- usage tracker concurrency ----------
def test_usage_tracker_thread_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    from agentic_engine.core.usage import UsageTracker
    import threading

    t = UsageTracker(path=tmp_path / "u.jsonl")

    def worker():
        for _ in range(50):
            t.record("solo", "qwen-plus", 100, 50)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    # No partial lines / corruption: every line is valid JSON.
    import json
    lines = (tmp_path / "u.jsonl").read_text().splitlines()
    assert len(lines) == 400
    for ln in lines:
        json.loads(ln)


# ---------- server auth ----------
def test_server_auth_open_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    monkeypatch.delenv("AGENTIC_ADMIN_KEY", raising=False)
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    # Re-import server fresh so its module-level state picks up env changes.
    import importlib
    import agentic_engine.server as srv
    importlib.reload(srv)

    from fastapi.testclient import TestClient
    client = TestClient(srv.app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["auth_required"] is False


def test_server_auth_required_when_admin_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    monkeypatch.setenv("AGENTIC_ADMIN_KEY", "supersecret")
    from agentic_engine.config import Settings
    import agentic_engine.config as cfg
    cfg._settings = Settings.load()

    import importlib
    import agentic_engine.server as srv
    importlib.reload(srv)

    from fastapi.testclient import TestClient
    client = TestClient(srv.app)
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["auth_required"] is True

    # Without header: 401
    r = client.get("/usage")
    assert r.status_code == 401

    # With wrong header: 401
    r = client.get("/usage", headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 401

    # With correct admin key: 200
    r = client.get("/usage", headers={"X-Admin-Key": "supersecret"})
    assert r.status_code == 200

    # Issue an H5 token via admin then use it
    r = client.post("/h5/token", headers={"X-Admin-Key": "supersecret"})
    assert r.status_code == 200
    tok = r.json()["token"]
    r = client.get("/usage", headers={"X-H5-Token": tok})
    assert r.status_code == 200


def test_token_store_ttl_expiry():
    from agentic_engine.server import _TokenStore
    s = _TokenStore()
    tok = s.issue(ttl=1)
    assert s.check(tok)
    time.sleep(1.1)
    assert not s.check(tok)
