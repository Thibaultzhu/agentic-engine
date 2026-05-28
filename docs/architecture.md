# agentic-engine 架构设计

本文件解释 **本项目** 的设计选择。它独立于任何上游项目；所有命名、模块边界、
API 都是为本仓库量身定制的。

## 目标

- **小** — 全部 core 代码 < 1000 行 Python，能在一晚读完。
- **可调试** — 不引入运行时元编程或 DSL；Agent 只是一个数据类加一个 while 循环。
- **跑得起来** — 默认指向阿里云百炼 OpenAI 兼容端点，开箱可用。
- **可演进** — 五个 core 原语相互正交，新增能力只需扩展工具或换模型。

## 五原语

```
+-------------+    uses     +-----------+
|   Agent     |-----------> |  Tool[]   |
+-------------+             +-----------+
       |                          ^
       | reads at start           | invokes
       v                          |
+-------------+             +-----------+
|  Memory     |             |   LLM     |  (Bailian / Qwen)
+-------------+             +-----------+
       ^
       | injects skill body
+-------------+
| SkillReg.   |
+-------------+

           composed by
+-------------+
| Orchestrator| ---> sequential | parallel | team-dispatch
+-------------+
```

### Agent — `core/agent.py`

A dataclass plus `run()`. The loop is the standard tool-calling pattern:

1. Build `messages`: `[system, user]`. The system message folds in the agent's
   own prompt, plus an optional bootstrap dump of `Memory`.
2. Send to the LLM with the agent's tool list.
3. If the response carries `tool_calls`, execute each one (subject to the
   permission mode), append a `tool` message per call, loop.
4. Otherwise, return the assistant content as `AgentResult.output`.

The maximum-turn cap is a hard guard: nothing magic happens at the limit, the
agent simply yields an `[max_turns reached]` output and lets the caller decide.

### Tool — `core/tool.py`

A `@tool(...)` decorator inspects the wrapped function's signature and type
hints to produce an OpenAI-compatible JSON schema. This means writing a new
tool is just writing a Python function — no manual schema authoring.

Every tool carries two flags:

- `read_only` — pure-read tools (Read, Grep, list_dir) are safe to auto-allow
  under stricter permission modes.
- `requires_approval` — tools that mutate or execute (write_file, bash_run)
  flip this on, so the permission layer can intercept.

### Orchestrator — `core/orchestrator.py`

Three composition modes, all using the same `Agent.run` underneath:

- `run_sequential([a, b, c], "goal")` — output of `a` is the input of `b`.
- `run_parallel({"a": "...", "b": "..."})` — `ThreadPoolExecutor` fans out.
- `dispatch(leader, goal)` — leader plans (JSON of subtasks), members execute
  in parallel, leader consolidates.

Background / cron-style execution is delegated to whatever scheduler the host
prefers (your shell, systemd, the user's existing cron tool); this framework
deliberately does not embed one.

### Memory — `core/memory.py`

Plain markdown files under `~/.agentic-engine/memory/`. Four scopes:

| Scope     | What goes here                                                |
|-----------|---------------------------------------------------------------|
| user      | Identity, role, preferences. Stable across projects.          |
| feedback  | Concrete corrections of the agent's behaviour.                |
| project   | Things you can't infer from code or git history.              |
| reference | Pointers to dashboards, tickets, runbooks.                    |

Plus `memory/daily/YYYY-MM-DD.md` for unstructured per-day scratch. The
bootstrap injection only pulls the four scope files, so daily logs stay out of
the prompt budget.

### SkillRegistry — `core/skills.py`

A skill is a folder containing `SKILL.md`. Frontmatter declares `name`,
`description`, `version`, `triggers`. The body is free-form markdown the agent
reads when the skill is selected.

Lookup order (later wins on name collision):

1. `<repo>/skills/`
2. `~/.agentic-engine/skills/`
3. `./.agentic/skills/` (project-local)

`registry.find(query)` returns matching skills by trigger substring; agents can
then concatenate the body into their system prompt.

## Permission model — `core/permissions.py`

Five modes, each documenting a different risk posture:

| Mode            | Behaviour                                              |
|-----------------|--------------------------------------------------------|
| `default`       | Tool needs approval ⇒ ask `approval_hook`              |
| `plan`          | Every tool call requires approval                      |
| `accept_edits`  | Read-only tools auto-allowed; writes still ask         |
| `bypass`        | Anything goes (only for trusted automation)            |
| `dont_ask`      | Reject anything not pre-allowed                        |

The `Agent.approval_hook` is just a callable `(tool_name, args) -> bool`. CLIs
prompt the user; servers check an ACL; tests return `True` unconditionally.

## LLM client — `llm/__init__.py`

Single function: `chat(messages, model, tools, temperature, extra_body)`. It
wraps the official `openai` SDK pointed at Bailian's compatible endpoint, so
any OpenAI-shaped API (Qwen, DeepSeek, vLLM, Ollama with `--api`) works as a
drop-in.

Region is selected once at startup from `AGENTIC_REGION=cn|sg`. Failover
between regions is delegated to the caller — wrap `chat()` in a `try/except`
and re-call with `make_client(api_key=other_key, base_url=other_url)`.

## Adapters — `adapters/`

`IMAdapter` is a two-method ABC: `send(chat_id, text)` and `listen(callback)`.
Concrete classes (`FeishuAdapter`, `DingTalkAdapter`) implement only what their
target platform needs. The framework does not bundle a webhook server — wire
the callback to your own FastAPI / Flask route.

## Teams — `teams/`

Pre-baked compositions return ready-to-run `Orchestrator` instances:

- `build_dev_team()` — PM → Architect → Developer → Reviewer → Tester.
- `build_research_team()` — Scout → Analyst → Reporter.

Each is ~30 lines; copy and adapt rather than configure.

## Trade-offs we accepted

- **No async.** Agents block; `run_parallel` uses threads. Most LLM workloads
  are I/O-bound, threads are simpler, and async would make the code bigger
  without measurable gain at this scale.
- **No vector DB.** Memory is markdown plus substring search. If you need
  semantic retrieval, plug Chroma or LanceDB into a custom tool — don't bake
  it into core.
- **No GUI.** A desktop client is a big separate project. The CLI plus the
  optional FastAPI server cover headless and remote use cases. Anyone wanting
  a UI should consume the HTTP endpoints.
