"""Smoke tests — no real LLM calls, just import + structural checks."""
import importlib


def test_import_root():
    m = importlib.import_module("agentic_engine")
    assert hasattr(m, "Agent")
    assert hasattr(m, "Tool")
    assert hasattr(m, "Orchestrator")
    assert hasattr(m, "Memory")
    assert hasattr(m, "SkillRegistry")
    assert hasattr(m, "PermissionMode")


def test_tool_decorator_registers():
    from agentic_engine.core.tool import registry, tool

    @tool(name="_t_demo", description="demo")
    def _demo(x: int, y: str = "z") -> str:
        return f"{x}-{y}"

    reg = registry()
    assert "_t_demo" in reg
    assert reg["_t_demo"].parameters["properties"]["x"]["type"] == "integer"


def test_memory_scopes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_HOME", str(tmp_path))
    import agentic_engine.config as cfg
    from agentic_engine.config import Settings
    cfg._settings = Settings.load()
    from agentic_engine.core.memory import Memory
    m = Memory()
    m.add("user", "I prefer concise answers")
    assert "concise answers" in m.read("user")
    hits = m.search("concise")
    assert hits and hits[0][0] == "user"


def test_skill_registry(tmp_path):
    sk_dir = tmp_path / "skills" / "demo"
    sk_dir.mkdir(parents=True)
    (sk_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill.\nversion: 0.1.0\ntriggers:\n  - demo\n---\n\n# Body",
        encoding="utf-8",
    )
    from agentic_engine.core.skills import SkillRegistry
    reg = SkillRegistry(search_paths=[tmp_path / "skills"])
    assert reg.get("demo") is not None
    assert reg.find("please run demo")
