"""agentic_engine — original multi-agent framework on Bailian / Qwen.

Public API (v0.3.0):
    Core      : Agent, AgentResult, Tool, tool, Orchestrator, Memory,
                SkillRegistry, PermissionMode, PermissionPolicy, Rule
    Ops layer : SessionStore, CronManager, UsageTracker, MCPClient,
                MCPHTTPClient, add_worktree, list_worktrees
    Auth      : Role, User, make_jwt, verify_jwt, user_from_token
    Pricing   : estimate, convert, REGION_PRICING
    RAG       : RAGMemory
    Eval      : Task, EvalReport, run_eval, load_tasks
    Logging   : get_logger, configure
    Telemetry : setup_tracing, span
    Plugins   : load_plugins
"""
from .core.agent import Agent, AgentResult
from .core.auth import Role, User, make_jwt, user_from_token, verify_jwt
from .core.cron import CronJob, CronManager
from .core.mcp import MCPClient, MCPError, MCPTool
from .core.mcp_http import MCPHTTPClient
from .core.memory import Memory
from .core.orchestrator import Orchestrator
from .core.permissions import PermissionMode, PermissionPolicy, Rule
from .core.pricing import REGION_PRICING, convert, estimate
from .core.rag import RAGMemory
from .core.sessions import Project, Session, SessionStore
from .core.skills import SkillRegistry
from .core.tool import Tool, tool
from .core.usage import UsageRecord, UsageTracker, default_tracker
from .core.worktree import WorktreeHandle, add_worktree, list_worktrees
from .evals import EvalReport, Task, load_tasks, run_eval
from .logging import configure as configure_logging
from .logging import get_logger
from .plugins import load_plugins
from .telemetry import setup_tracing, span

__all__ = [
    # Core
    "Agent", "AgentResult", "Tool", "tool", "Orchestrator", "Memory",
    "SkillRegistry", "PermissionMode", "PermissionPolicy", "Rule",
    # Ops
    "SessionStore", "Project", "Session",
    "CronManager", "CronJob",
    "UsageTracker", "UsageRecord", "default_tracker",
    "MCPClient", "MCPError", "MCPTool", "MCPHTTPClient",
    "add_worktree", "list_worktrees", "WorktreeHandle",
    # Auth
    "Role", "User", "make_jwt", "verify_jwt", "user_from_token",
    # Pricing
    "estimate", "convert", "REGION_PRICING",
    # RAG
    "RAGMemory",
    # Eval
    "Task", "EvalReport", "run_eval", "load_tasks",
    # Logging / Telemetry / Plugins
    "get_logger", "configure_logging",
    "setup_tracing", "span",
    "load_plugins",
]
__version__ = "0.3.0"
