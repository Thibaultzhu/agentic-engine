# Quickstart

## Install

```bash
# Using pip
pip install "agentic-engine[server,auth,log,otel,rag,ratelimit]"

# Or for a hacking checkout
git clone https://github.com/Thibaultzhu/agentic-engine.git
cd agentic-engine
pip install -e ".[dev]"
```

## Configure Bailian / Qwen

```bash
export DASHSCOPE_API_KEY="sk-..."
# Pick your region: cn (Hangzhou) or sg (Singapore)
export AGENTIC_REGION="cn"
```

## Run an agent locally

```python
from agentic_engine import Agent
from agentic_engine.tools import bash_run, read_file, web_fetch

agent = Agent(
    name="planner",
    role="general-purpose",
    tools=[read_file, bash_run, web_fetch],
)

print(agent.run("Summarise the README.md in 3 bullets.").output)
```

## Stream tokens

```python
for piece in agent.run_stream("Tell me a joke about FastAPI."):
    print(piece, end="", flush=True)
```

## Boot the HTTP server

```bash
export AGENTIC_ADMIN_KEY="changeme"
export AGENTIC_JWT_SECRET="$(openssl rand -hex 32)"

uvicorn agentic_engine.server:app --host 127.0.0.1 --port 8765
```

* `GET  /health` — version & uptime
* `POST /chat` — sync turn
* `POST /chat/stream` — SSE (`text/event-stream`)
* `WS   /ws/chat` — bidirectional streaming
* `POST /auth/token` — issue JWT (admin-only)
* `GET  /me` — introspect bearer
* `POST /eval` — run an `evals/golden/*.json` task

## Schedule recurring jobs

```python
from agentic_engine import CronManager

mgr = CronManager()
mgr.add(
    name="daily-news",
    schedule={"kind": "cron", "expr": "0 9 * * *"},
    payload={"type": "agent_turn", "message": "Summarise yesterday's commits."},
    max_retries=2, retry_backoff_s=30,
)
```

Failed jobs land in `~/.agentic-engine/cron.dlq.jsonl` for manual replay.
