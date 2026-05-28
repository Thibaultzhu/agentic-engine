# Changelog

See the canonical [CHANGELOG.md](https://github.com/Thibaultzhu/agentic-engine/blob/main/CHANGELOG.md)
in the repo root for the authoritative version history.

## Highlights

### 0.3.0 — 2026-05-28

* Async-first agent (`run_async`, `run_stream`, `run_stream_async`) and
  `chat_stream` LLM helper.
* Server: SSE `/chat/stream`, WebSocket `/ws/chat`, JWT `/auth/token` & `/me`.
* Auth: HS256 JWT with `python-jose` fallback, role-based dependencies.
* RAG: `RAGMemory` with chromadb auto-detect + `_BM25Lite` fallback.
* Permissions: `Rule`/`PermissionPolicy` with glob matching + JSON persistence.
* Bash sandbox: cwd allowlist (incl. system temp by default), rlimits,
  bwrap / sandbox-exec wrappers.
* Cron: `max_retries`, `retry_backoff_s`, dead-letter queue (`cron.dlq.jsonl`).
* MCP HTTP/SSE transport (`MCPHTTPClient`).
* Postgres adapter (`PostgresSessionStore`, lazy `psycopg` import).
* SQLite WAL + busy_timeout for multi-process safety.
* Multi-region pricing (`cn`/`sg`/`us`) + FX conversion via USD bridge.
* Plugin system via Python entry points (`agentic_engine.tools`).
* Eval harness (`Task`, `EvalReport`, `run_eval`) with `evals/golden/`.
* Rate limit (`slowapi`) wrapper with `AGENTIC_RATELIMIT_DISABLE` bypass.
* OpenTelemetry tracing via `setup_tracing()` / `span()`.
* Structured logging via structlog with stdlib fallback.
* CI matrix (3.10–3.12), ruff + mypy + pip-audit + bandit, OIDC PyPI release.
* PEP 561 (`py.typed`), MIT license, mkdocs-material site.

### 0.2.1 — 2026-05-28
Round-2 hardening: P0 + P1 + P2 from the internal code review.

### 0.2.0 — 2026-05-27
Phase 2: sessions, cron, usage tracking, MCP, computer-use, Telegram, H5, desktop scaffolding.

### 0.1.0 — 2026-05-26
Initial public release of the original multi-agent framework.
