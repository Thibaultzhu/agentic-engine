# agentic-engine

> An original multi-agent engineering framework for building agentic AI workflows on top of Bailian (DashScope) Qwen models.

`agentic-engine` is a small, opinionated Python framework. It gives you the
five primitives you actually need to build production multi-agent systems —
`Agent`, `Tool`, `Orchestrator`, `Memory`, `SkillRegistry` — and nothing else.

It is **not** a port or fork of any closed-source product. The design draws on
publicly known patterns from CrewAI, AutoGen, LangGraph, and the OpenAI Agents
SDK, then re-expresses them in a single, readable Python codebase.

---

## Quick start

```bash
git clone https://github.com/Thibaultzhu/agentic-engine.git
cd agentic-engine
python -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env
# edit .env and set DASHSCOPE_API_KEY_SG (or _CN)

agentic version
agentic chat "List the current directory and tell me what kind of project this is."
agentic dev-team "Build a tiny CLI that counts lines/words/chars."
```

## Concepts

**Agent** — one role with a system prompt, a tool list, a permission mode, and
an autonomous tool-calling loop on top of the OpenAI-compatible Bailian API.

**Tool** — a Python function decorated with `@tool(...)`. The decorator infers a
JSON schema from your type hints, so you write idiomatic Python and get
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

## Configuration

| Env var                  | Purpose                                |
|--------------------------|----------------------------------------|
| `AGENTIC_REGION`         | `cn` or `sg` — chooses Bailian region  |
| `DASHSCOPE_API_KEY_CN/SG`| API key for the matching region        |
| `DASHSCOPE_BASE_URL_CN/SG`| Override the OpenAI-compatible base URL |
| `AGENTIC_MODEL_DEFAULT`  | Default model (e.g. `qwen-plus`)       |
| `AGENTIC_MODEL_FAST`     | Fast / cheap fallback                  |
| `AGENTIC_MODEL_STRONG`   | Heavy reasoning (e.g. `qwen3-max`)     |
| `AGENTIC_HOME`           | Storage root (default `~/.agentic-engine`) |

## Layout

```
agentic_engine/
├── core/         # Agent, Tool, Orchestrator, Memory, SkillRegistry, PermissionMode
├── llm/          # Bailian / OpenAI-compatible client
├── tools/        # bash_run, read_file, write_file, list_dir, grep_text, web_fetch
├── adapters/     # IM channel adapters (Feishu, DingTalk stubs)
├── teams/        # Pre-built role compositions (dev_team, research_team)
├── cli.py        # `agentic` CLI
└── server.py     # Optional FastAPI HTTP server
skills/           # Bundled skills
examples/         # Runnable demos
docs/             # Architecture docs and a study of the cc-haha pattern
```

## CLI

```
agentic version                               # show config
agentic chat "..."                            # one-shot single-agent
agentic dev-team "build X"                    # 5-role pipeline
agentic skills                                # list discovered skills
agentic memory show --scope user              # print memory file
agentic memory add  --scope feedback --text "Be concise"
agentic memory search --text concise
```

## HTTP server

```
uvicorn agentic_engine.server:app --port 9120
curl -X POST localhost:9120/chat -H 'content-type: application/json' \
     -d '{"message":"hello"}'
```

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
