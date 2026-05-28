# agentic-engine

> An original multi-agent engineering framework for building agentic AI workflows on top of Bailian (DashScope) Qwen models.

`agentic-engine` is a small, opinionated Python framework. Version `0.2.0`
extends the original five primitives — `Agent`, `Tool`, `Orchestrator`,
`Memory`, `SkillRegistry` — with a full operations layer: persistent
sessions, scheduled tasks, token-usage tracking, MCP tool servers, git
worktree isolation, computer-use tools, and a thin web/desktop shell.

It is **not** a port or fork of any closed-source product. The design draws on
publicly known patterns from CrewAI, AutoGen, LangGraph, and the OpenAI Agents
SDK, then re-expresses them in a single, readable Python codebase.

---

## Quick start

```bash
git clone https://github.com/Thibaultzhu/agentic-engine.git
cd agentic-engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[full]"

cp .env.example .env
# edit .env and set DASHSCOPE_API_KEY_SG (or _CN)

agentic version
agentic chat "List the current directory and tell me what kind of project this is."
agentic dev-team "Build a tiny CLI that counts lines/words/chars."
```

## Primitives

**Agent** — one role with a system prompt, a tool list, a permission mode, and
an autonomous tool-calling loop on top of any OpenAI-compatible API.

**Tool** — a Python function decorated with `@tool(...)`. The decorator infers
a JSON schema from your type hints, so you write idiomatic Python and get
function-calling for free.

**Orchestrator** — composes agents. Three modes: `run_sequential` pipes outputs
through a chain, `run_parallel` fans out to a thread pool, and `dispatch`
implements team-leader → workers → consolidation.

**Memory** — file-backed persistent knowledge with four scopes (`user`,
`feedback`, `project`, `reference`) plus daily logs. Bootstrap content is
auto-injected into the system prompt at the start of each agent run.

**SkillRegistry** — markdown-based plugins. Drop a `SKILL.md` with YAML
frontmatter into `skills/`, `~/.agentic-engine/skills/`, or
`./.agentic/skills/` and it's discovered automatically.

## Operations layer (0.2)

| Module                         | Purpose                                              |
|--------------------------------|------------------------------------------------------|
| `core.sessions.SessionStore`   | sqlite multi-project, multi-conversation history     |
| `core.worktree`                | `git worktree` helpers for parallel agent runs       |
| `core.mcp.MCPClient`           | minimal stdio JSON-RPC 2.0 client for MCP tool servers |
| `core.cron.CronManager`        | APScheduler-backed jobs persisted to JSON            |
| `core.usage.UsageTracker`      | jsonl token ledger + per-model cost rollups          |
| `tools.diff`                   | `git_status` / `git_diff` / `git_log` as tools       |
| `tools.screen`                 | screen capture, mouse, keyboard (computer-use)       |
| `adapters.TelegramAdapter`     | Telegram Bot API (long-polling)                      |
| `adapters.WeChatAdapter`       | WeChat Work group bot webhook                        |
| `llm.PROVIDERS`                | bailian-cn / bailian-sg / deepseek / openai / ollama |

## Configuration

| Env var                  | Purpose                                |
|--------------------------|----------------------------------------|
| `AGENTIC_REGION`         | `cn` or `sg` — chooses Bailian region  |
| `DASHSCOPE_API_KEY_CN/SG`| API key for the matching region        |
| `DASHSCOPE_BASE_URL_CN/SG`| Override the OpenAI-compatible base URL |
| `DEEPSEEK_API_KEY`       | DeepSeek API key                       |
| `OPENAI_API_KEY`         | OpenAI API key                         |
| `OLLAMA_BASE_URL`        | Ollama base url (default `http://localhost:11434/v1`) |
| `TELEGRAM_BOT_TOKEN`     | Telegram bot token from @BotFather     |
| `WECHAT_WORK_WEBHOOK`    | WeChat Work group bot webhook URL      |
| `AGENTIC_ADMIN_KEY`      | Admin secret for issuing H5 tokens     |
| `AGENTIC_HOME`           | Storage root (default `~/.agentic-engine`) |

## Layout

```
agentic_engine/
├── core/      Agent, Tool, Orchestrator, Memory, SkillRegistry, Permissions,
│              SessionStore, WorktreeHandle, MCPClient, CronManager, UsageTracker
├── llm/       Multi-provider OpenAI-compatible client + usage tracking
├── tools/     bash, files, web, diff (git), screen (computer-use)
├── adapters/  IMAdapter ABC + Feishu / DingTalk / Telegram / WeChat
├── teams/     dev_team (5 roles), research_team (3 roles)
├── cli.py     `agentic` CLI (chat / dev-team / sessions / cron / usage / worktree / serve)
└── server.py  FastAPI: /chat /dev-team /sessions /cron /usage + H5 /h5/*
desktop/web/   Static HTML console (works as Tauri webview content)
skills/        Bundled skills (code-review, doc-writer)
examples/      Runnable demos
docs/          Architecture docs and a high-level study of the cc-haha pattern
```

## CLI

```
agentic version
agentic chat "..."                                       # one-shot single agent
agentic dev-team "build X"                               # 5-role pipeline
agentic serve --port 9120                                # start HTTP server

agentic skills
agentic memory show --scope user

agentic sessions ls
agentic sessions new --project myapp --title "design review"
agentic sessions show <session-id>

agentic cron ls
agentic cron add daily --cron "0 9 * * *" --message "summarize yesterday's git log"
agentic cron rm <id>

agentic usage --days 7
agentic usage --json

agentic worktree add /path/to/repo --branch feature/spike
agentic worktree ls
```

## HTTP server

```
agentic serve --port 9120
curl -X POST localhost:9120/chat -H 'content-type: application/json' \
     -d '{"message":"hello"}'
curl localhost:9120/usage
curl localhost:9120/sessions
```

H5 access (e.g. for sharing a single-shot mobile chat link):

```
export AGENTIC_ADMIN_KEY=$(openssl rand -hex 16)
agentic serve --port 9120 &
TOKEN=$(curl -s -X POST localhost:9120/h5/token -H "X-Admin-Key: $AGENTIC_ADMIN_KEY" | jq -r .token)
open "http://localhost:9120/h5/page?token=$TOKEN"
```

## Desktop UI

`desktop/web/index.html` is a self-contained 3-pane console that talks to
`localhost:9120`. Open it in any browser, or wrap it with Tauri:

```
open desktop/web/index.html              # or
python -m http.server 8000 --directory desktop/web
```

See `desktop/README.md` for the optional Tauri wrap.

## Examples

- `examples/single_agent.py` — minimal one-agent loop
- `examples/parallel_research.py` — three scouts fan out
- `examples/dev_team_demo.py` — PM → Architect → Dev → Reviewer → Tester

## Docs

- [`docs/architecture.md`](docs/architecture.md) — design of `agentic-engine`
- [`docs/cc-haha-architecture-study.md`](docs/cc-haha-architecture-study.md) — high-level study of the cc-haha pattern (no source reproduction)
- [`docs/usage.md`](docs/usage.md) — fuller usage manual

## License

MIT.

## Disclaimer

This project is original code. It is not a port, fork, or derivative of any
closed-source product. The accompanying study of the cc-haha pattern in
`docs/cc-haha-architecture-study.md` describes only publicly documented
high-level concepts.
