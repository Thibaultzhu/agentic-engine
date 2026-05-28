"""Agent — single conversational role with tool access and memory.

Implements a tool-calling loop on top of the OpenAI-compatible Bailian API.
Each Agent owns its own message history and can be run multiple turns.

Robustness knobs:
    tool_result_max_chars  : truncate giant tool outputs (default 8000).
    history_window         : keep at most N most-recent non-system messages
                             when sending the next request (default 40).
                             system + the final user/tool block always kept.
    transient_retries      : retry on 429 / 5xx / connection errors (default 3).
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rich.console import Console

from ..config import get_settings
from ..llm import chat, chat_stream
from .memory import Memory
from .permissions import PermissionMode
from .tool import Tool

if TYPE_CHECKING:  # pragma: no cover
    from .sessions import SessionStore

_console = Console()
logger = logging.getLogger(__name__)


_TRANSIENT_HINTS = (
    "rate limit", "rate_limit", "timeout", "timed out",
    "connection", "temporarily unavailable", "overloaded",
    "internal server error", "bad gateway", "service unavailable",
    "gateway timeout", " 429", " 500", " 502", " 503", " 504",
)


def _is_transient(err: Exception) -> bool:
    s = str(err).lower()
    return any(h in s for h in _TRANSIENT_HINTS)


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
    approval_hook: Callable[[str, dict[str, Any]], bool] | None = None
    tool_result_max_chars: int = 8000
    history_window: int = 40
    transient_retries: int = 3
    # Optional persistence — when both store and session_id are set, every
    # assistant/tool turn is appended to the session.
    store: SessionStore | None = None
    session_id: str | None = None
    autosave: bool = True
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

    # ---------- llm call with retry ----------
    def _chat_with_retry(self, messages: list[dict[str, Any]], **kw: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.transient_retries + 1):
            try:
                return chat(messages=messages, agent_name=self.name, **kw)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt >= self.transient_retries or not _is_transient(e):
                    raise
                delay = min(20.0, (2 ** attempt) * (0.5 + random.random()))
                logger.warning("[agent %s] transient LLM error (attempt %d): %s — retry in %.1fs",
                               self.name, attempt + 1, e, delay)
                time.sleep(delay)
        # Unreachable, but mypy-friendly.
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")

    # ---------- history compaction ----------
    def _compact(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.history_window <= 0 or len(messages) <= self.history_window + 1:
            return messages
        # Always keep the system message at index 0.
        head = messages[:1]
        tail = messages[-self.history_window:]
        # Don't break a tool_calls/tool pair across the boundary: if first kept
        # message is a tool response, also keep the assistant tool_calls msg.
        if tail and tail[0].get("role") == "tool":
            # Walk back to last assistant with tool_calls
            i = messages.index(tail[0])
            while i > 0 and not (
                messages[i].get("role") == "assistant" and messages[i].get("tool_calls")
            ):
                i -= 1
            tail = messages[i:]
        return head + tail

    # ---------- persistence ----------
    def _persist(self, role: str, content: str) -> None:
        if not (self.autosave and self.store and self.session_id):
            return
        try:
            self.store.append(self.session_id, role, content)  # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001
            logger.debug("session autosave failed: %s", e)

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
        self._persist("user", user_input)

        tool_calls_total = 0
        for turn in range(self.max_turns):
            resp = self._chat_with_retry(
                self._compact(messages),
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
                self._persist("assistant", msg.content or "")
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
                content = str(result)
                if len(content) > self.tool_result_max_chars:
                    content = (
                        content[: self.tool_result_max_chars]
                        + f"\n[...truncated {len(content) - self.tool_result_max_chars} chars]"
                    )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })

        return AgentResult(
            agent=self.name,
            output="[max_turns reached]",
            tool_calls=tool_calls_total,
            turns=self.max_turns,
            raw_messages=messages,
        )

    # ---------- async + streaming ----------
    async def run_async(self, user_input: str, verbose: bool = False) -> AgentResult:
        """Async wrapper around :meth:`run` — offloads to a worker thread."""
        return await asyncio.to_thread(self.run, user_input, verbose)

    def run_stream(self, user_input: str) -> Iterator[str]:
        """Stream assistant text. No tool-calling — pure generation.

        For a tool-calling stream you still want :meth:`run` (final answer).
        Yields content deltas as they arrive from the LLM.
        """
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
        self._persist("user", user_input)
        out_parts: list[str] = []
        for piece in chat_stream(
            messages=messages,
            model=self.model or s.model_default,
            temperature=self.temperature,
        ):
            out_parts.append(piece)
            yield piece
        self._persist("assistant", "".join(out_parts))

    async def run_stream_async(self, user_input: str) -> AsyncIterator[str]:
        """Async generator equivalent of :meth:`run_stream`.

        Each underlying chunk arrives synchronously from the OpenAI client; we
        yield it from a worker thread so the async event loop is not blocked.
        """
        loop = asyncio.get_event_loop()
        gen = self.run_stream(user_input)

        def _next() -> str | None:
            try:
                return next(gen)
            except StopIteration:
                return None

        while True:
            piece = await loop.run_in_executor(None, _next)
            if piece is None:
                break
            yield piece
