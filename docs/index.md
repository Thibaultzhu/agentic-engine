# Agentic Engine

[![PyPI](https://img.shields.io/pypi/v/agentic-engine?color=blueviolet)](https://pypi.org/project/agentic-engine/)
[![CI](https://github.com/Thibaultzhu/agentic-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/Thibaultzhu/agentic-engine/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/agentic-engine.svg)](https://pypi.org/project/agentic-engine/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **local-first**, **single-process** agentic engine for Alibaba Cloud
**Bailian (DashScope) Qwen** models. Designed to be ergonomic for daily
work — no cloud control plane, no vendor lock-in, every artefact lives
on disk.

## Why this exists

* **Original design.** Not a fork of any closed-source product.
* **Multi-agent native.** `Agent`, `Orchestrator`, `Team` are first-class.
* **Local everything.** SQLite (WAL) sessions, JSONL cron history, BM25
  RAG fallback. Postgres is opt-in.
* **Streaming + async.** SSE, WebSocket, `run_async`, `run_stream_async`.
* **Sandboxed by default.** Bash tool ships rlimit + cwd allowlist +
  bwrap / sandbox-exec wrappers.
* **Observability by default.** structlog + OpenTelemetry, both optional.
* **Plug-in friendly.** Third-party tools register through Python entry
  points.

## What's in the box (v0.3.0)

| Layer        | Module                                          |
|--------------|-------------------------------------------------|
| Core         | `Agent`, `Tool`, `Orchestrator`, `Memory`       |
| Persistence  | `SessionStore` (SQLite WAL), `PostgresSessionStore`, `CronManager` |
| Bridges      | `MCPClient`, `MCPHTTPClient`                    |
| Memory / RAG | `RAGMemory` (chromadb auto-detect → BM25 fallback) |
| Auth         | JWT HS256 with `python-jose` fallback           |
| Pricing      | Multi-region (`cn`/`sg`/`us`) + FX conversion   |
| Server       | FastAPI: `/chat`, `/chat/stream`, `/ws/chat`, `/auth/token`, `/eval` |
| Ops          | `slowapi` rate-limit, OTel tracing, structlog   |
| Eval         | `Task`, `EvalReport`, regex/contains/llm judge  |

## Read next

* [Quickstart](quickstart.md) — install, run, ship.
* [Agent loop](concepts/agent.md) — how `run`, `run_async`, `run_stream` work.
* [HTTP API](server/http.md) — every endpoint and its auth surface.
* [Changelog](changelog.md) — what shipped, what to upgrade.
