"""Agent — single conversational role with tool access and memory.

Implements a tool-calling loop on top of the OpenAI-compatible Bailian API.
Each Agent owns its own message history and can be run multiple turns.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from rich.console import Console

from ..config import get_settings
from ..llm import chat
from .memory import Memory
from .permissions import PermissionMode
from .tool import Tool


_console = Console()


@dataclass
class AgentResult:
    agent: str
    output: str
    tool_calls: int = 0
    turns: int = 0
    raw_messages: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Agent:
    name: str
    role: str = "general-purpose"
    system_prompt: str = ""
    tools: list[Tool] = field(default_factory=list)
    model: str | None = None
    permission: PermissionMode = PermissionMode.DEFAULT
    max_turns: int = 8
    temperature: float = 0.6
    memory: Memory | None = None
    use_bootstrap_memory: bool = True
    approval_hook: Callable[[str, dict[str, Any]], bool] | None = None  # name, args -> approve?
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    # ---------- tool helpers ----------
    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self.tools]

    def _tool_by_name(self, name: str) -> Tool | None:
        for t in self.tools:
            if t.name == name:
                return t
        return None

    def _check_permission(self, t: Tool, args: dict[str, Any]) -> bool:
        if self.permission == PermissionMode.BYPASS:
            return True
        if self.permission == PermissionMode.DONT_ASK:
            return not t.requires_approval
        if self.permission == PermissionMode.ACCEPT_EDITS and t.read_only:
            return True
        if t.requires_approval or self.permission == PermissionMode.PLAN:
            if self.approval_hook:
                return self.approval_hook(t.name, args)
            return True
        return True

    # ---------- main loop ----------
    def run(self, user_input: str, verbose: bool = True) -> AgentResult:
        s = get_settings()
        sys_parts = [self.system_prompt or f"You are {self.name}, a {self.role} agent."]
        if self.memory and self.use_bootstrap_memory:
            mem_block = self.memory.bootstrap_block().strip()
            if mem_block:
                sys_parts.append("# Persistent memory\n" + mem_block)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "\n\n".join(sys_parts)},
            {"role": "user", "content": user_input},
        ]

        tool_calls_total = 0
        for turn in range(self.max_turns):
            resp = chat(
                messages=messages,
                model=self.model or s.model_default,
                tools=self._tool_schemas() if self.tools else None,
                temperature=self.temperature,
            )
            msg = resp.choices[0].message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            if not msg.tool_calls:
                if verbose:
                    _console.print(f"[bold cyan]{self.name}[/]: {msg.content}")
                return AgentResult(
                    agent=self.name,
                    output=msg.content or "",
                    tool_calls=tool_calls_total,
                    turns=turn + 1,
                    raw_messages=messages,
                )

            for tc in msg.tool_calls:
                tool_calls_total += 1
                tname = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool = self._tool_by_name(tname)
                if not tool:
                    result = f"[error] tool '{tname}' not registered"
                elif not self._check_permission(tool, args):
                    result = f"[denied] permission denied for '{tname}'"
                else:
                    if verbose:
                        _console.print(f"[dim]{self.name} → {tname}({args})[/]")
                    try:
                        result = tool(**args)
                    except Exception as e:  # noqa: BLE001
                        result = f"[error] {type(e).__name__}: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result)[:8000],
                })

        return AgentResult(
            agent=self.name,
            output="[max_turns reached]",
            tool_calls=tool_calls_total,
            turns=self.max_turns,
            raw_messages=messages,
        )
