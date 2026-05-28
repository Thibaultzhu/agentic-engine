"""agentic_engine — original multi-agent framework on Bailian / Qwen.

Public API:
    Agent, Tool, Orchestrator, Memory, SkillRegistry, PermissionMode
"""
from .core.agent import Agent
from .core.tool import Tool, tool
from .core.orchestrator import Orchestrator
from .core.memory import Memory
from .core.skills import SkillRegistry
from .core.permissions import PermissionMode

__all__ = [
    "Agent",
    "Tool",
    "tool",
    "Orchestrator",
    "Memory",
    "SkillRegistry",
    "PermissionMode",
]
__version__ = "0.1.0"
