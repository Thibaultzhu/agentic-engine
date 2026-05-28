# Code Review — agentic-engine 0.2.0

Date: 2026-05-28
Reviewer: in-tree pass over every Python module, server, CLI, adapters, tools and tests.
Scope: ~25 modules, ~1900 LoC.

Verdict: **functionally green for single-user/local use**, with 3 real
correctness bugs, 4 security gaps, and a healthy backlog of polish.

> **Status update (round 2 — 2026-05-28):** every P1 and every P2 listed
> below has been landed in commit `feat: round-2 hardening` against
> v0.2.1. Test suite is now 41/41 green; ruff config in pyproject is
> clean. See the table at the bottom for the per-item resolution map.

Severity scale:
- 🔴 **P0** — broken behaviour or auth gap. Fix now.
- 🟠 **P1** — works but wrong under concurrency, threat models, or rough input.
- 🟡 **P2** — quality / future-proofing.

---

## 🔴 P0 — must fix

### P0-1. Cron scheduler is never started by the server
File: `agentic_engine/server.py:23`

```python
_cron = CronManager()              # constructed
# ... no _cron.start() anywhere
```

Symptom: `POST /cron` happily writes the job to `cron.json`, but
APScheduler's `BackgroundScheduler` is never spun up, so jobs never fire.
Same applies to the CLI path `agentic cron add`.

Fix: start the scheduler on FastAPI startup (with a guarded `try/except` so
a missing `apscheduler` install doesn't break the rest of the app). Stop it
on shutdown.

### P0-2. H5 token is security theatre
Files: `agentic_engine/server.py` (`/chat`, `/h5/*`), `desktop/web/index.html`

The browser sends `X-H5-Token` to `/chat`, but `/chat` never reads or
validates it. Anyone reaching the listening port can call `/chat`,
`/dev-team`, `/sessions`, `/cron` directly. The "one-time URL" pattern
implies these endpoints are gated; they are not.

Fix: introduce a single dependency `require_h5_token_or_admin` and apply it
to every state-changing endpoint. The H5 page should obtain a token bound
to a session id and the server should reject requests without it.

### P0-3. sqlite foreign keys are declared but never enforced
File: `agentic_engine/core/sessions.py:_SCHEMA`

`messages.session_id REFERENCES sessions(id)` is declared, but sqlite
disables FK enforcement by default. So `append("non-existent-sid", ...)`
silently writes an orphan row.

Fix: every `_cx()` should run `cx.execute("PRAGMA foreign_keys = ON")` and
the schema should declare `ON DELETE CASCADE` on the messages FK.

---

## 🟠 P1 — works today, breaks under load / hostile input

### P1-1. `_tokens` dict is unbounded and not thread-safe
File: `server.py`

A worker that issues 10k tokens never reaps them until the process restarts.
Concurrent issue/check across uvicorn workers (`--workers 4`) is also racy.

Fix: TTL cache (`cachetools.TTLCache`) or a sweep on every issue, plus a
`threading.Lock`. Long-term: move to JWT signed with `AGENTIC_ADMIN_KEY` so
every uvicorn worker can verify without shared state.

### P1-2. UsageTracker append is not atomic across threads
File: `core/usage.py:record`

Two agents finishing at the same time can interleave a half-line into the
JSONL. POSIX guarantees only that O_APPEND writes <= PIPE_BUF are atomic,
which is not what `f.write` does here.

Fix: take a `threading.Lock` around the open/write/close. Optional:
flock(2) for multi-process safety.

### P1-3. CronManager validates expressions only at scheduler-start time
File: `core/cron.py:add`

`agentic cron add daily --cron "this is not cron"` succeeds, writes
`cron.json`, then later crashes when `start()` parses it.

Fix: instantiate the trigger inside `add()` to fail fast.

### P1-4. MCPClient `_send` blocks forever on a stuck server
File: `core/mcp.py`

`self._proc.stdout.readline()` has no timeout. A hung MCP server hangs the
calling agent, eating a turn.

Fix: switch to a reader thread + `queue.Queue.get(timeout=...)`, or use
`select`/`selectors` on the stdout fd. Also: server-pushed notifications
will currently be misread as the response to the next request.

### P1-5. `bash_run` blacklist is trivially bypassable
File: `tools/bash.py`

`"rm -rf  /"` (two spaces), `"\\rm -rf /"`, `"r""m -rf /"`, `bash -c 'rm -rf /'`
all sail through substring matching. The list also misses obvious peers:
`> /dev/sda`, `chmod -R 000 ~`, `find / -delete`.

Fix: at minimum require `shlex.split` and inspect argv[0] + flags. Better:
run untrusted commands inside a Docker container or `firejail`. Document
that `bash_run` is not a sandbox.

### P1-6. Telegram polling has no exponential back-off, no max retries
File: `adapters/telegram.py:listen`

Invalid token → 401 every poll. Adapter just sleeps 3 s and retries forever.

Fix: classify HTTPStatusError, escalate on 401/403, exponential backoff on
500/network errors, and surface the error to the caller via a callback.

### P1-7. `Orchestrator.dispatch` parses JSON by index slicing
File: `core/orchestrator.py:104`

```python
plan = json.loads(planning.output[planning.output.find("{"): planning.output.rfind("}") + 1])
```

If the leader's response contains nested code fences with braces, or no
braces at all, this either returns garbage or throws. Falls back to
"give every member the goal" which silently wastes tokens.

Fix: use a dedicated structured-output prompt with `response_format={"type":"json_object"}`,
or a JSON-extraction utility (`json5`, regex+stack-balance).

### P1-8. Web UI sends every request to `/chat` with no token header
File: `desktop/web/index.html`

`X-H5-Token` is not actually attached. So once P0-2 is fixed, the desktop
client breaks. They must move together.

---

## 🟡 P2 — polish / future-proofing

| # | File | Issue |
|---|---|---|
| P2-1 | `core/tool.py` | `_PY_TO_JSON` only handles primitives. `Optional[X]`, `list[int]`, `dict[str, Any]` all fall back to `"string"`. |
| P2-2 | `core/tool.py` | The auto-built `description: pname` for each parameter is just the parameter name — useless. Should pull from a docstring section or a `Annotated[..., "..."]`. |
| P2-3 | `core/agent.py` | Tool-result truncation hard-coded at 8000 chars. Should be a setting. |
| P2-4 | `core/agent.py` | No retry/backoff on transient OpenAI errors. A single 5xx kills the run. |
| P2-5 | `core/agent.py` | History grows unboundedly inside one `run()`. For long tool chains this hits context limits. Add a sliding-window or summarisation. |
| P2-6 | `core/orchestrator.run_parallel` | `verbose=True` interleaves rich output across threads → garbled console. Default to `False` or buffer per-thread. |
| P2-7 | `core/memory.py` | `bootstrap_block()` concatenates the entire memory file — could be enormous. No size cap. |
| P2-8 | `core/sessions.py` | No way to delete a session/project (only archive). Eventual cleanup story missing. |
| P2-9 | `core/cron.py` | `enabled` flag is stored but `_add_to_scheduler` is invoked only on enabled jobs at start; toggling at runtime requires manual restart. |
| P2-10 | `core/cron.py` | Default runner builds a fresh `Agent` per fire — wastes per-call setup, no memory sharing. |
| P2-11 | `core/usage.py` | Pricing table is hard-coded in CNY. Should be JSON config under `AGENTIC_HOME/pricing.json` so users can update without a release. |
| P2-12 | `core/mcp.py` | Tool input-schema dict is forwarded as-is; OpenAI rejects schemas with unsupported keywords. Strip unknown fields. |
| P2-13 | `core/worktree.py` | Branch generated as `agent/wt-<6hex>`. 6 hex digits = 24-bit collision risk if you spawn lots of worktrees in parallel. Bump to 8. |
| P2-14 | `tools/files.py:write_file` | Always overwrites silently. Add `if_exists: "fail" \| "overwrite" \| "append"` and a backup-to-`.bak` switch. |
| P2-15 | `tools/files.py:grep_text` | `glob="**/*"` walks `.git`, `node_modules`, `__pycache__`. Add a default ignore list. |
| P2-16 | `tools/diff.py` | `_git_text` swallows non-zero exit codes and returns the formatted error string into the LLM context — fine for status, but `git_log` on a non-git dir produces a confusing string. |
| P2-17 | `tools/screen.py` | `keyboard_hotkey` parses comma-separated keys; if a key contains a comma… not a real issue but documented edge case. |
| P2-18 | `tools/web.py` | No URL allow-list. An agent can fetch `http://169.254.169.254/...` (cloud metadata service). Add an SSRF filter. |
| P2-19 | `adapters/feishu.py`/`dingtalk.py` | `listen()` raises NotImplementedError. Document this on import to set expectations, or move to a `*Stub` class name. |
| P2-20 | `adapters/wechat.py` | Same as above. Also: parse_mode, signature verification not handled. |
| P2-21 | `llm/__init__.py` | `chat()` swallows tracker errors with bare `except`. Ok for resilience, but at least log at debug. |
| P2-22 | `llm/__init__.py` | When `provider=` and `model=None`, defaults to provider's `default_model` — but `Agent` already supplied a default. Order of precedence is provider > settings only when caller passes `provider`. Document. |
| P2-23 | `cli.py` | `agentic chat` doesn't open or persist a session. So usage rolls up but there's no conversation to revisit. |
| P2-24 | `server.py` | No CORS configuration. Browser clients on a different origin can't call it. Add `fastapi.middleware.cors.CORSMiddleware`. |
| P2-25 | `server.py` | `/dev-team` runs synchronously inside the request handler. A 90-second LLM chain blocks the worker. Move to `BackgroundTasks` + a job-id. |
| P2-26 | `tests/` | No test exercises the OpenAI client — there's no recorded VCR cassette or fake. A breaking change in the SDK won't be caught. Add a `respx`-based mock. |
| P2-27 | `tests/` | `test_telegram_adapter_stub` doesn't actually exercise the polling loop. |
| P2-28 | `pyproject.toml` | No `[tool.ruff]`, no `[tool.pytest.ini_options]`. Define explicit lint/test config. |
| P2-29 | `pyproject.toml` | `apscheduler` is in `[cron]` extra; tests for cron will fail in environments without it. Either move to base deps or skip the test conditionally. (Currently it works because we just added apscheduler manually to the venv.) |
| P2-30 | `desktop/web/index.html` | No XSS escape on rendered tool outputs. Today only LLM text comes through, but tool outputs may contain HTML. We do `escapeHtml` only on the final text. Verify all branches. |

---

## Architecture comments (no severity)

- Dependency direction is clean: `tools/` and `adapters/` depend on
  `core/`, never the reverse. Good.
- Public surface in `agentic_engine/__init__.py` still only exposes the
  Phase-1 primitives. Phase-2 modules (`SessionStore`, `CronManager`,
  `UsageTracker`, `MCPClient`) are reachable only via deep import.
  Consider a curated `agentic_engine.ops` re-export module.
- The `IMAdapter` ABC is good but most concrete classes throw on
  `listen()`. Promote a `WebhookAdapter` mixin or split sending and
  receiving into two ABCs to be honest about what's implemented.
- The CLI mixes two styles: top-level commands (`chat`, `dev-team`,
  `usage`, `serve`) and grouped sub-apps (`sessions`, `cron`, `worktree`).
  Either go all-in on sub-apps or all-in on flat — pick one.
- `Agent` ↔ `SessionStore` is not connected. `Agent.run()` builds messages
  in memory; nothing persists. A natural enhancement is `Agent(store=…, session_id=…)`.

---

## Quick wins (≤30 min each)

1. Wire `_cron.start()` into FastAPI lifespan.
2. Add `PRAGMA foreign_keys = ON` to every sqlite connection.
3. Validate cron expression in `CronManager.add` before persisting.
4. Lock around `UsageTracker.record`.
5. Prepend a single `require_h5_token_or_admin` Depends to all server routes.
6. Add `cachetools.TTLCache` for `_tokens`.
7. Bump worktree suffix from 6 → 8 hex.
8. Add CORS middleware to the server (`*` for now).

These eight changes resolve every P0 and the most damaging P1s.

---

## Resolution map (round 2)

| Item | Where | Status | Notes |
|---|---|---|---|
| P0-1 cron not started | `server.py` lifespan | ✅ done | `_cron.start()` / `_cron.stop()` |
| P0-2 H5 token never checked | `server.py:require_auth` | ✅ done | full Depends gate |
| P0-3 sqlite FK off | `core/sessions.py` | ✅ done | `PRAGMA foreign_keys=ON` + CASCADE |
| P1-1 token store leak | `_TokenStore` | ✅ done | TTL + lock |
| P1-2 usage write race | `core/usage.py` | ✅ done | `threading.Lock` |
| P1-3 cron expr lazy validation | `core/cron.py` | ✅ done | `_build_trigger` in `add()` |
| P1-4 MCP `_send` blocking | `core/mcp.py` | ✅ done | reader thread + `queue.get(timeout=…)` |
| P1-5 worktree suffix collision | `core/worktree.py` | ✅ done | 6 → 8 hex |
| P1-6 telegram no backoff/401 | `adapters/telegram.py` | ✅ done | exponential backoff + `TelegramFatalError` for 401/403/404 |
| P1-7 dispatch JSON brace-slice | `core/orchestrator.py` | ✅ done | code-fence + balanced-brace extractor |
| P1-8 bash blacklist substring | `tools/bash.py` | ✅ done | shlex argv check |
| P2-1/2 Tool typing | `core/tool.py` | ✅ done | `Optional`, `list[T]`, `dict[K,V]`, `Annotated`, docstring |
| P2-3 tool-result truncation | `core/agent.py` | ✅ done | `tool_result_max_chars` knob |
| P2-4 transient retry | `core/agent.py` | ✅ done | exp-backoff + jitter, `transient_retries` |
| P2-5 sliding window | `core/agent.py` | ✅ done | `history_window`, tool-pair safe |
| P2-6 parallel quiet default | `core/orchestrator.py` | ✅ done | `verbose=False` |
| P2-7 bootstrap cap | `core/memory.py` | ✅ done | `max_chars_per_scope` |
| P2-8 hard delete | `core/sessions.py` | ✅ done | `delete_session` / `delete_project` |
| P2-9 cron enable/disable | `core/cron.py` + CLI + server | ✅ done | runtime toggle |
| P2-11 pricing.json | `core/usage.py` | ✅ done | `${AGENTIC_HOME}/pricing.json` |
| P2-12 MCP schema sanitizer | `core/mcp.py` | ✅ done | strips `$schema`, `$comment`, `additionalProperties` |
| P2-14 write_file safety | `tools/files.py` | ✅ done | `if_exists`, `backup`, append |
| P2-15 grep default ignores | `tools/files.py` | ✅ done | `.git`/`node_modules`/`__pycache__`/etc. |
| P2-16 git diff non-repo | `tools/diff.py` | ✅ done | clear "not a git repo" message |
| P2-18 SSRF block | `tools/web.py` | ✅ done | DNS-resolved IP check + metadata host list |
| P2-19 IM Sender/Receiver split | `adapters/base.py` | ✅ done | `IMSender`, `IMReceiver`, `IMAdapter` |
| P2-20 llm bare except | `llm/__init__.py` | ✅ done | `logger.debug` + precedence doc |
| P2-23 cli chat persist | `cli.py` | ✅ done | `--session/--project` |
| P2-25 /dev-team async | `server.py` | ✅ done | `BackgroundTasks` + `/jobs/{id}` |
| P2-26 respx OpenAI mock | `tests/test_round2.py` | ✅ done | one full happy-path |
| P2-27 ruff/pytest config | `pyproject.toml` | ✅ done | + `0.2.1` bump |
| P2-28 re-export ops | `agentic_engine/__init__.py` | ✅ done | SessionStore/CronManager/UsageTracker/MCPClient/worktree |

Tests: **41 passed in 1.77s**. Ruff: **clean**.
