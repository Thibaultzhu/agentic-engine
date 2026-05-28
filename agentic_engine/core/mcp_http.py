"""MCP HTTP / streamable-HTTP client — best-effort, optional.

The official MCP open spec defines two remote transports:
    1. ``streamable_http``  — single ``POST`` that returns an SSE stream.
    2. plain HTTP request/response over JSON-RPC 2.0 (used for ``tools/list``
       and ``tools/call`` once the server has been initialised).

This module ships a small client for the second case (request/response),
which is enough to bridge ordinary remote MCP servers as agent tools. The
streamable variant is implemented as an iterator over the SSE body.

The class deliberately mirrors the public surface of
:class:`agentic_engine.core.mcp.MCPClient` (``initialize``, ``list_tools``,
``call_tool``, ``as_tools``) so callers can swap implementations.
"""
from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from .mcp import MCPError, MCPTool, _sanitize_schema  # type: ignore[attr-defined]


@dataclass
class MCPHTTPClient:
    base_url: str
    headers: dict[str, str] | None = None
    timeout: float = 30.0
    _session_id: str | None = None
    _initialized: bool = False

    # ---------- low-level ----------
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        h = dict(self.headers or {})
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        try:
            r = httpx.post(self.base_url, json=payload, headers=h, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise MCPError(f"http error: {e}") from e
        if r.status_code >= 400:
            raise MCPError(f"http {r.status_code}: {r.text[:200]}")
        # Capture session id on first request if the server sets one.
        sid = r.headers.get("Mcp-Session-Id")
        if sid and not self._session_id:
            self._session_id = sid
        try:
            return r.json()
        except json.JSONDecodeError as e:
            raise MCPError(f"non-JSON response: {r.text[:200]}") from e

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        rid = uuid.uuid4().hex[:12]
        envelope = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            envelope["params"] = params
        resp = self._post(envelope)
        if "error" in resp:
            raise MCPError(f"{method} → {resp['error']}")
        return resp.get("result")

    # ---------- public ----------
    def initialize(self, client_name: str = "agentic-engine", client_version: str = "0.3") -> Any:
        if self._initialized:
            return None
        result = self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": client_version},
        })
        # Spec: client must follow up with a notification — fire-and-forget.
        with contextlib.suppress(MCPError):
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True
        return result

    def list_tools(self) -> list[MCPTool]:
        if not self._initialized:
            self.initialize()
        result = self._rpc("tools/list") or {}
        out: list[MCPTool] = []
        for t in result.get("tools", []):
            out.append(MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=_sanitize_schema(t.get("inputSchema", {})),
            ))
        return out

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self._initialized:
            self.initialize()
        return self._rpc("tools/call", {"name": name, "arguments": arguments})

    # SSE streaming variant — best-effort, requires server to support it.
    def stream(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:  # pragma: no cover
        h = dict(self.headers or {})
        h.setdefault("Accept", "text/event-stream")
        with httpx.stream("POST", self.base_url, json=payload, headers=h,
                         timeout=None) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    if body:
                        try:
                            yield json.loads(body)
                        except json.JSONDecodeError:
                            continue


__all__ = ["MCPHTTPClient"]
