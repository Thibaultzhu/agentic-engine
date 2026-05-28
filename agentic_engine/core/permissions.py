"""Permission modes — governs how an Agent handles risky operations."""
from __future__ import annotations

from enum import Enum


class PermissionMode(str, Enum):
    DEFAULT = "default"          # Ask user for risky actions
    PLAN = "plan"                # Every action requires explicit approval
    ACCEPT_EDITS = "accept_edits"  # Auto-accept file edits, ask others
    BYPASS = "bypass"            # Skip all checks (dangerous)
    DONT_ASK = "dont_ask"        # Reject anything not pre-approved
