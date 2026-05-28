# architecture

`agentic-engine` is structured in three layers.

## Layer 1 — primitives (`core/`)

The five primitives that every multi-agent framework eventually rediscovers:

- `Agent` — owns a system prompt, a tool set, a permission mode, an LLM
  client and a tool-calling loop with a turn budget. The loop runs
  user → LLM → (tool calls?) → tool execution → LLM → … until the model
  emits a final assistant message or the budget is exhausted.
- `Tool` — a Python function decorated with `@tool(...)`. The decorator
  inspects the function signature, builds a JSON schema from the type hints
  and registers the tool in a process-global registry. Each tool carries
  `read_only` and `requires_approval` flags consumed by the permission gate.
- `PermissionMode` — `default` / `plan` / `accept_edits` / `bypass` /
  `dont_ask`. Modelled after how real engineering teams treat sandboxed vs
  unrestricted execution. The agent calls `policy.check(tool)` before every
  invocation; the result drives an optional approval hook.
- `Memory` — file-backed under `~/.agentic-engine/`, with four scopes
  (`user`, `feedback`, `project`, `reference`) plus daily logs. The
  bootstrap block is injected into the system prompt at run-start.
- `SkillRegistry` — markdown plugins. A skill is a directory containing
  `SKILL.md` with YAML frontmatter (name, description, version, triggers).
  Three search paths: bundled `./skills/`, user `~/.agentic-engine/skills/`,
  project `./.agentic/skills/`.

`Orchestrator` composes agents in three modes: sequential pipe, parallel
fan-out (thread pool), and dispatch (leader → workers → consolidator).

## Layer 2 — operations (`core/sessions.py`, `core/cron.py`, `core/usage.py`, `core/mcp.py`, `core/worktree.py`)

Production agents need bookkeeping the framework should provide instead of
forcing every user to invent it.

- `SessionStore` (sqlite) — `projects`, `sessions`, `messages` tables. New
  conversations are scoped to a project; a project is scoped to a directory
  on disk. `append`, `history`, `archive`, `rename` cover the full CRUD.
- `CronManager` — APScheduler `BackgroundScheduler` driven by JSON-persisted
  jobs. Each job carries a `payload` consumed by a runner; the default
  runner builds a fresh `Agent` and runs `payload["message"]` non-interactively.
- `UsageTracker` — every successful LLM call is recorded as a JSONL line
  with prompt/completion tokens, model and CNY cost estimate. `summary()`
  rolls up by model.
- `MCPClient` — minimal stdio JSON-RPC 2.0 client following the public MCP
  spec. `as_tools()` wraps each remote tool as a local `Tool` so MCP
  servers participate in the regular tool-calling loop.
- `add_worktree(repo, branch)` — wraps `git worktree add`. Long-running or
  destructive agent runs get their own checkout under
  `<repo>/../.agentic-worktrees/`.

## Layer 3 — surfaces (`cli.py`, `server.py`, `adapters/`, `desktop/`)

- `cli.py` — `typer` app exposing every subsystem (`chat`, `dev-team`,
  `sessions`, `cron`, `usage`, `worktree`, `skills`, `memory`, `serve`).
- `server.py` — FastAPI HTTP server. Health, chat, dev-team, sessions
  CRUD, cron CRUD, usage rollup, plus `/h5/token` + `/h5/page` for
  short-lived public sharing.
- `adapters/` — IM channel abstractions. `IMAdapter` is the ABC; current
  implementations: `FeishuAdapter`, `DingTalkAdapter` (webhook stubs),
  `TelegramAdapter` (live, long-polling), `WeChatAdapter` (group bot
  webhook, one-way).
- `desktop/web/index.html` — single-file 3-pane console (sessions, log,
  status). Talks to the FastAPI server over plain JSON. A Tauri wrap is
  optional and described in `desktop/README.md`.

## Multi-provider LLM client

`llm/__init__.py` keeps a `PROVIDERS` table:

| key          | base_url                                                           | default model     |
|--------------|--------------------------------------------------------------------|-------------------|
| bailian-cn   | https://dashscope.aliyuncs.com/compatible-mode/v1                  | qwen-plus         |
| bailian-sg   | https://dashscope-intl.aliyuncs.com/compatible-mode/v1             | qwen-plus         |
| deepseek     | https://api.deepseek.com/v1                                        | deepseek-chat     |
| openai       | https://api.openai.com/v1                                          | gpt-4o-mini       |
| ollama       | http://localhost:11434/v1                                          | qwen2.5:7b        |

`chat(..., provider="deepseek")` swaps the client; agents stay unchanged.

## Data on disk

Everything lives under `${AGENTIC_HOME:-~/.agentic-engine}`:

```
~/.agentic-engine/
├── memory/             # user.md, feedback.md, project.md, reference.md, YYYY-MM-DD.md
├── sessions.db         # sqlite SessionStore
├── usage.jsonl         # token-usage ledger
├── cron.json           # scheduled jobs
└── skills/             # user-level skills
```

## Design properties

- **Original** — every module is written from scratch; the cc-haha source
  is cited only conceptually in `docs/cc-haha-architecture-study.md`.
- **Optional dependencies** — APScheduler, pyautogui, mss are only needed
  for cron and computer-use; the package installs and tests pass without
  them.
- **Provider-agnostic** — anything OpenAI-compatible plugs in via
  `PROVIDERS`. No model is hard-coded into agent logic.
- **Single-process by default** — orchestration uses threads, not heavy
  IPC. Worktrees + session ids give logical isolation when you need it.
