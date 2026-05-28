"""MCP (Model Context Protocol) stdio client — minimal implementation.

Implements the JSON-RPC 2.0 framing over stdio defined by the public MCP
specification. Supports:
    - initialize handshake
    - tools/list  → list available tools on the server
    - tools/call  → invoke a tool, return its result content
    - shutdown    → graceful close

This is a thin, dependency-free client; for production use consider the
official `mcp` SDK. We keep it small for transparency.
"""
from __future__ import annotations

import json
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


class MCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        self.command = command
        self.env = env
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._next_id = 0

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
        self._initialize()

    def stop(self) -> None:
        if not self._proc:
            return
        try:
            self._send("shutdown", {})
        except Exception:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._proc = None

    # ---------- transport ----------
    def _send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise RuntimeError("MCP client not started")
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            self._proc.stdin.write(json.dumps(req) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed pipe")
            resp = json.loads(line)
            if "error" in resp:
                raise RuntimeError(f"MCP error: {resp['error']}")
            return resp.get("result", {})

    def _initialize(self) -> None:
        self._send(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "clientInfo": {"name": "agentic-engine", "version": "0.2.0"},
                "capabilities": {"tools": {}},
            },
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

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._send("tools/call", {"name": name, "arguments": arguments})
        # Result usually has {"content": [{"type": "text", "text": "..."}]}
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
        """Return list of agentic_engine Tool objects wrapping each MCP tool."""
        from .tool import Tool

        tools_meta = self.list_tools()
        out: list[Tool] = []
        client = self
        for meta in tools_meta:
            def _make_handler(n: str):
                def _h(**kwargs: Any) -> Any:
                    return client.call_tool(n, kwargs)
                _h.__name__ = n
                return _h
            t = Tool(
                name=f"mcp_{meta.name}",
                description=meta.description or f"MCP tool {meta.name}",
                handler=_make_handler(meta.name),
                parameters=meta.input_schema or {
                    "type": "object", "properties": {}, "required": [],
                },
                read_only=False,
                requires_approval=True,
            )
            out.append(t)
        return out
