"""MCP (Model Context Protocol) stdio client — minimal, robust.

Implements the JSON-RPC 2.0 framing over stdio defined by the public MCP
specification. Supports:
    - initialize handshake
    - tools/list  → list available tools on the server
    - tools/call  → invoke a tool, return its result content
    - shutdown    → graceful close

Robustness:
    - Background reader thread + queue with timeout, so a stuck server
      never hangs the agent loop.
    - Server-pushed notifications are dropped silently (we do not subscribe).
    - Schema fields the OpenAI tool schema does not understand are stripped.
"""
from __future__ import annotations

import contextlib
import json
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any

_OPENAI_SCHEMA_KEYS = {
    "type", "properties", "required", "items", "enum", "description",
    "default", "minimum", "maximum", "minLength", "maxLength", "pattern",
    "anyOf", "oneOf", "allOf",
}

# Keys whose values are dicts of arbitrary names → schema (not schema keywords).
_NAMED_SUBSCHEMA_KEYS = {"properties", "definitions", "$defs", "patternProperties"}


def _sanitize_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        out: dict[str, Any] = {}
        for k, v in schema.items():
            if k not in _OPENAI_SCHEMA_KEYS:
                continue
            if k in _NAMED_SUBSCHEMA_KEYS and isinstance(v, dict):
                out[k] = {name: _sanitize_schema(sub) for name, sub in v.items()}
            else:
                out[k] = _sanitize_schema(v)
        return out
    if isinstance(schema, list):
        return [_sanitize_schema(x) for x in schema]
    return schema


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None,
                 default_timeout: float = 30.0):
        self.command = command
        self.env = env
        self.default_timeout = default_timeout
        self._proc: subprocess.Popen | None = None
        self._send_lock = threading.Lock()
        self._next_id = 0
        # id -> Queue (each waiter has its own one-shot queue)
        self._pending: dict[int, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stopped = threading.Event()

    # ---------- lifecycle ----------
    def start(self) -> None:
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=self.env,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._initialize()

    def stop(self) -> None:
        if not self._proc:
            return
        self._stopped.set()
        with contextlib.suppress(Exception):
            self._send("shutdown", {}, timeout=2.0)
        try:
            self._proc.terminate()
            self._proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._proc = None

    # ---------- transport ----------
    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            if self._stopped.is_set():
                return
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            mid = msg.get("id")
            if mid is None:
                # Notification — ignore (no subscriber model in this client).
                continue
            with self._pending_lock:
                q = self._pending.pop(mid, None)
            if q:
                q.put(msg)

    def _send(self, method: str, params: dict[str, Any],
              timeout: float | None = None) -> dict[str, Any]:
        if not self._proc or not self._proc.stdin:
            raise MCPError("MCP client not started")
        timeout = timeout if timeout is not None else self.default_timeout
        with self._send_lock:
            self._next_id += 1
            req_id = self._next_id
            q: queue.Queue = queue.Queue(maxsize=1)
            with self._pending_lock:
                self._pending[req_id] = q
            req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            self._proc.stdin.write(json.dumps(req) + "\n")
            self._proc.stdin.flush()
        try:
            resp = q.get(timeout=timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(req_id, None)
            raise MCPError(f"MCP timeout after {timeout}s on method '{method}'") from None
        if "error" in resp:
            raise MCPError(f"MCP error: {resp['error']}")
        return resp.get("result", {})

    def _initialize(self) -> None:
        self._send(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "clientInfo": {"name": "agentic-engine", "version": "0.2.0"},
                "capabilities": {"tools": {}},
            },
            timeout=10.0,
        )
        # Some servers expect an "initialized" notification afterwards.
        if self._proc and self._proc.stdin:
            self._proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            )
            self._proc.stdin.flush()

    # ---------- public API ----------
    def list_tools(self) -> list[MCPTool]:
        result = self._send("tools/list", {})
        out = []
        for t in result.get("tools", []):
            out.append(MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema") or t.get("input_schema") or {},
            ))
        return out

    def call_tool(self, name: str, arguments: dict[str, Any],
                  timeout: float | None = None) -> Any:
        result = self._send("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            return "\n".join(parts)
        return json.dumps(result, ensure_ascii=False)

    # ---------- bridge to local Tool registry ----------
    def as_tools(self) -> list:
        from .tool import Tool

        tools_meta = self.list_tools()
        out: list[Tool] = []
        client = self
        for meta in tools_meta:
            schema = _sanitize_schema(meta.input_schema) or {
                "type": "object", "properties": {}, "required": [],
            }

            def _make_handler(n: str):
                def _h(**kwargs: Any) -> Any:
                    return client.call_tool(n, kwargs)
                _h.__name__ = n
                return _h

            t = Tool(
                name=f"mcp_{meta.name}",
                description=meta.description or f"MCP tool {meta.name}",
                handler=_make_handler(meta.name),
                parameters=schema,
                read_only=False,
                requires_approval=True,
            )
            out.append(t)
        return out
