"""Smoke tests for Phase-2 modules — sessions / cron / usage / providers."""


def test_sessions_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    import agentic_engine.config as cfg
    from agentic_engine.config import Settings
    cfg._settings = Settings.load()

    from agentic_engine.core.sessions import SessionStore
    store = SessionStore()
    p = store.upsert_project("demo", str(tmp_path))
    s = store.new_session(p.id, "first chat")
    store.append(s.id, "user", "hello")
    store.append(s.id, "assistant", "hi there")
    msgs = store.history(s.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    sessions = store.list_sessions(project_id=p.id)
    assert len(sessions) == 1


def test_usage_tracker(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    import agentic_engine.config as cfg
    from agentic_engine.config import Settings
    cfg._settings = Settings.load()

    from agentic_engine.core.usage import UsageTracker, estimate_cost
    t = UsageTracker(path=tmp_path / "u.jsonl")
    t.record("solo", "qwen-plus", 1000, 500)
    t.record("solo", "qwen-plus", 2000, 800)
    summary = t.summary()
    assert summary["calls"] == 2
    assert summary["total_tokens"] == 4300
    assert summary["by_model"]["qwen-plus"]["calls"] == 2
    assert estimate_cost("qwen-plus", 1_000_000, 0) > 0


def test_cron_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    import agentic_engine.config as cfg
    from agentic_engine.config import Settings
    cfg._settings = Settings.load()

    from agentic_engine.core.cron import CronManager
    mgr = CronManager()
    job = mgr.add(
        "noon-report",
        {"kind": "cron", "expr": "0 12 * * *"},
        {"type": "agent_turn", "message": "hi"},
    )
    # reload from disk
    mgr2 = CronManager()
    ids = [j.id for j in mgr2.list()]
    assert job.id in ids
    mgr2.remove(job.id)
    assert all(j.id != job.id for j in CronManager().list())


def test_providers_table():
    from agentic_engine.llm import PROVIDERS
    assert "bailian-cn" in PROVIDERS
    assert "bailian-sg" in PROVIDERS
    assert "deepseek" in PROVIDERS
    assert PROVIDERS["bailian-sg"].base_url.startswith("https://")


def test_diff_tool_registered():
    from agentic_engine.tools import git_diff, git_log, git_status
    assert git_status.name == "git_status"
    assert git_diff.read_only is True
    assert git_log.read_only is True


def test_screen_tool_lazy():
    # Should import even if pyautogui/mss aren't installed
    from agentic_engine.tools import mouse_click, screen_grab
    assert screen_grab.name == "screen_grab"
    assert mouse_click.requires_approval is True


def test_telegram_adapter_stub():
    from agentic_engine.adapters import TelegramAdapter, WeChatAdapter
    # Token absent → send returns False but does not raise
    t = TelegramAdapter(token="")
    assert t.send("123", "hi") is False
    w = WeChatAdapter(webhook="")
    assert w.send("g1", "hi") is False
