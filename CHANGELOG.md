# Changelog

All notable changes to **agentic-engine** are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-05-28

A comprehensive feature push covering the 27-item optimisation backlog.

### Added
- **Async-first agent surface**: `Agent.run_async()`, `run_stream()`,
  `run_stream_async()` + LLM helper `chat_stream()`.
- **Server streaming**: SSE `/chat/stream`, WebSocket `/ws/chat` endpoints.
- **JWT authentication**: HS256 issuance (`/auth/token`) + bearer auth via
  `python-jose` fallback. `require_role()` dependency factory.
- **RAGMemory**: chromadb auto-detect + `_BM25Lite` pure-Python fallback.
- **Permission policy engine**: `Rule` / `PermissionPolicy` with glob matching,
  JSON persistence, session-level `.remember()`.
- **Bash sandbox hardening**: cwd allowlist (env `AGENTIC_BASH_CWD_ALLOW`),
  POSIX rlimits (`RLIMIT_AS`, `RLIMIT_CPU`), bwrap and sandbox-exec wrappers.
- **Cron retry + dead-letter**: `max_retries`, `retry_backoff_s`, DLQ at
  `cron.dlq.jsonl`, run history via `.runs(job_id)`.
- **MCP HTTP/SSE transport**: `MCPHTTPClient` — JSON-RPC over HTTP with
  streamable-HTTP support.
- **PostgresSessionStore**: drop-in replacement for the SQLite store (lazy
  `psycopg` v3 import).
- **SQLite safety**: WAL mode + `busy_timeout=30s` + `BEGIN IMMEDIATE` for
  multi-process safety.
- **Multi-region pricing**: `cn`/`sg`/`us` rate tables + FX conversion via USD
  bridge.
- **Plugin system**: Python entry-points loader (`agentic_engine.tools` group).
- **Eval harness**: `Task`, `EvalReport`, `run_eval()` with regex/contains/llm
  judgement modes + `evals/golden/basic.json`.
- **Rate limit**: `slowapi` wrapper with `AGENTIC_RATELIMIT_DISABLE` bypass.
- **OpenTelemetry**: `setup_tracing()`, `span()` context manager (no-op without
  SDK).
- **Structured logging**: structlog with stdlib `_StdLibAdapter` fallback +
  `.bind()` API.
- **CI matrix**: GitHub Actions pytest 3.10–3.12 + ruff + mypy + pip-audit +
  bandit. OIDC PyPI release workflow.
- **PEP 561**: `py.typed` marker, MIT `LICENSE`.
- **Tauri desktop config**: `desktop/tauri.conf.json` + docs/README.
- **Security audit script**: `scripts/audit.sh` (bandit + pip-audit + ruff).
- **Mkdocs site**: `mkdocs.yml` (material theme) + full `docs/` tree (concepts,
  server, ops, reference).
- **`__all__`**: `agentic_engine/__init__.py` re-exports all public API symbols.
- 15 new test cases in `tests/test_v03.py` → total suite 56 tests.

### Changed
- `__version__` bumped to `0.3.0`.
- `pyproject.toml`: classifiers, keywords, URLs, `[project.entry-points]`,
  optional extras `[auth,log,otel,rag,ratelimit,docs,postgres]`, mypy + bandit
  tool config.

## [0.2.1] — 2026-05-28

Round-2 hardening sweep: every remaining P1 (3) and every P2 (30) from
`docs/CODE_REVIEW.md` is resolved on disk. Tests `41/41` green, ruff
clean.

### Added
- `core/mcp.py` — schema sanitizer for `as_tools()` (whitelisted JSON-schema
  keys, recurses correctly into `properties` / `definitions` / `$defs` /
  `patternProperties`).
- `core/tool.py` — full type-hint coverage: `Optional[T]`, `Union[...]`,
  `list[T]`, `tuple[T, ...]`, `dict[K, V]`, `Literal[...]` (→ `enum`),
  `Annotated[T, "desc"]`. Google-style docstring `Args:` parsing.
  JSON-serialisable defaults emitted as schema `default`.
- `core/agent.py` — `tool_result_max_chars=8000` truncation,
  `history_window=40` sliding window with tool-pair safety, and
  `transient_retries=3` exponential-backoff retry helper for 429/5xx/network.
- `core/orchestrator.py` — `_extract_json_object` fallback chain
  (raw → ```json fenced → balanced-bracket scan with string/escape state).
  `run_parallel(verbose=False)` is the new default.
- `core/memory.py` — `bootstrap_block(max_chars_per_scope=2048)` with
  line-aligned tail keep.
- `core/sessions.py` — `delete_session(sid)`, `delete_project(pid)`
  (CASCADE; rollback on error).
- `core/cron.py` — `enable(job_id)`, `disable(job_id)` runtime toggles
  syncing persisted state with the live scheduler.
- `core/usage.py` — pricing override via `${AGENTIC_HOME}/pricing.json`
  (per-1M input/output CNY).
- `tools/files.py` — `write_file(if_exists="overwrite|fail|append",
  backup=True)` and `grep_text` default ignore list (`.git`,
  `node_modules`, `__pycache__`, `.venv`, `dist`, `build`, etc.) plus
  `include_hidden`.
- `tools/diff.py` — `_is_git_repo` precheck, friendly error messages.
- `tools/web.py` — SSRF guard: scheme allowlist (`http`/`https` only),
  DNS-resolved IP refused on private/loopback/link-local/multicast/
  reserved/unspecified; metadata host blocklist; `allow_private=True`
  escape hatch.
- `adapters/base.py` — split into `IMSender` and `IMReceiver` ABCs;
  `IMAdapter` retained for back-compat.
- `adapters/telegram.py` — `TelegramFatalError` for 401/403/404; 429
  honours `retry_after`; 5xx/network use full-jitter exponential backoff
  with `max_consecutive_failures=10`; logging instead of `print`.
- `cli.py` — `chat --session SID --project NAME` auto-creates and
  persists turns; new `sessions rm`, `sessions rmproject` (with
  `typer.confirm`); new `cron enable`, `cron disable`.
- `server.py` — `POST /dev-team?async_=true` runs in `BackgroundTasks`,
  in-process `_JobStore`, `GET /jobs/{job_id}` for polling.
  `POST /cron/{id}/enable` and `POST /cron/{id}/disable` endpoints.
- `agentic_engine/__init__.py` — re-export `SessionStore`, `Project`,
  `Session`, `CronManager`, `CronJob`, `UsageTracker`, `UsageRecord`,
  `default_tracker`, `MCPClient`, `MCPError`, `MCPTool`, `add_worktree`,
  `list_worktrees`, `WorktreeHandle`, `AgentResult`.
- `pyproject.toml` — `[tool.ruff]` (line-length 110, py310, select
  `E/F/I/B/UP/N/SIM`, ignore `E501/B008/N818`), `[tool.pytest.ini_options]`
  (minversion 8, testpaths, addopts, deprecation filters); `respx` added
  to `[dev]` and `[full]` extras.
- `tests/test_round2.py` — 22 new tests covering every change above
  (Tool typing, dispatch JSON, memory cap, sessions delete, cron toggle,
  pricing override, MCP sanitizer, write_file safety, grep ignores,
  diff non-repo, SSRF blocking, Telegram 401 + 5xx escalation,
  agent retry / sliding window / truncation, server async + cron
  endpoints, IM split, top-level re-exports, llm via respx mock).

### Changed
- `core/mcp.py:_send` is no longer a blocking sequential read. A reader
  thread fans incoming messages into per-id `queue.Queue`s; `_send`
  blocks on the matching queue with a configurable `default_timeout=30s`
  and raises `MCPError` on timeout. Notifications without `id` are dropped.
- `llm/__init__.py` documents provider-selection precedence
  (explicit arg > model-prefix > settings) and replaces bare `except`
  with `logger.debug` calls.
- `core/orchestrator.py:run_parallel` defaults to `verbose=False`; member
  runs inside `dispatch` are silenced.

### Fixed
- MCP schema sanitizer no longer accidentally filters property *names*
  (only filters per-property *schemas*).
- `core/sessions.py` propagates SQLite errors with rollback in the
  context manager (was silently swallowing).
- Server cron / sessions exception chains use `raise … from e` (no more
  ruff `B904` warnings, clearer tracebacks).

### Tooling
- ruff: clean across `agentic_engine/`.
- pytest: **41 passed in 1.73s** (4 smoke + 7 phase-2 + 8 post-review +
  22 round-2).

## [0.2.0] — 2026-05-28

Phase-2 — agentic-engine grew an "ops" layer alongside the core
primitives.

### Added
- `core/sessions.py` — sqlite-backed projects/sessions/messages.
- `core/worktree.py` — git worktree helpers for parallel agents.
- `core/cron.py` — APScheduler-based cron/interval/date jobs.
- `core/usage.py` — JSONL token-usage tracker + cost estimator.
- `core/mcp.py` — minimal MCP stdio JSON-RPC 2.0 client and `as_tools()`
  bridge.
- `tools/diff.py` — git plumbing wrappers (status / diff / apply).
- `tools/screen.py` — computer-use primitives (mss screenshot, pyautogui
  click/type) with `requires_approval`.
- `adapters/telegram.py`, `adapters/wechat.py` — IM bridges.
- `desktop/` — minimal HTML5 control panel (`index.html`) wiring into
  `/h5/*` server endpoints.
- HTTP API: `/usage`, `/sessions/*`, `/cron/*`, `/h5/token`, `/h5/page`,
  session-aware `/chat`.
- CLI: `agentic sessions`, `agentic cron`, `agentic worktree`,
  `agentic usage`, `agentic serve` sub-typers.

### Changed
- `llm/__init__.py` — multi-provider table; `chat()` records usage.
- `core/agent.py` — passes `agent_name` into the usage tracker.
- README + `docs/architecture.md` + `docs/usage.md` rewritten to cover
  the three-layer view and every new surface.

## [0.1.0] — 2026-05-28

Initial scaffold — original multi-agent framework on Bailian / Qwen.

### Added
- `core/agent.py` — single-Agent loop with tool-call dispatch.
- `core/tool.py` — Python-function → JSON-schema decorator.
- `core/orchestrator.py` — Manager `dispatch()` over a member list and
  `run_parallel()` thread fan-out.
- `core/memory.py`, `core/skills.py`, `core/permissions.py`.
- `tools/bash.py`, `tools/files.py`, `tools/web.py`.
- `teams/dev_team.py`, `teams/research_team.py`.
- FastAPI server, Typer CLI, smoke tests, README, `docs/architecture.md`,
  `docs/usage.md`.

[0.2.1]: https://github.com/Thibaultzhu/agentic-engine/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Thibaultzhu/agentic-engine/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Thibaultzhu/agentic-engine/releases/tag/v0.1.0
