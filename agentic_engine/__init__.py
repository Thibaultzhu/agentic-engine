"""agentic_engine — original multi-agent framework on Bailian / Qwen.

Public API:
    Core      : Agent, Tool, tool, Orchestrator, Memory, SkillRegistry, PermissionMode
    Ops layer : SessionStore, CronManager, UsageTracker, MCPClient,
                add_worktree, list_worktrees
"""
from .core.agent import Agent, AgentResult
from .core.cron import CronJob, CronManager
from .core.mcp import MCPClient, MCPError, MCPTool
from .core.memory import Memory
from .core.orchestrator import Orchestrator
from .core.permissions import PermissionMode
from .core.sessions import Project, Session, SessionStore
from .core.skills import SkillRegistry
from .core.tool import Tool, tool
from .core.usage import UsageRecord, UsageTracker, default_tracker
from .core.worktree import WorktreeHandle, add_worktree, list_worktrees

__all__ = [
    # Core
    "Agent", "AgentResult", "Tool", "tool", "Orchestrator", "Memory",
    "SkillRegistry", "PermissionMode",
    # Ops
    "SessionStore", "Project", "Session",
    "CronManager", "CronJob",
    "UsageTracker", "UsageRecord", "default_tracker",
    "MCPClient", "MCPError", "MCPTool",
    "add_worktree", "list_worktrees", "WorktreeHandle",
]
__version__ = "0.2.1"
