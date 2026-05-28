# Sessions & Cron

## SessionStore (SQLite WAL)

```python
from agentic_engine import SessionStore

store = SessionStore()                # default path: ~/.agentic-engine/sessions.db
proj = store.upsert_project("agentic", "/Volumes/Lenovo/AI Agent项目/agentic-engine")
sess = store.start_session(proj.id, name="round-2")
store.append(sess.id, role="user", content="hi")
store.append(sess.id, role="assistant", content="hello!")

for m in store.messages(sess.id):
    print(m.role, m.content)
```

The connection is opened with:

* `journal_mode = WAL` — readers don't block writers.
* `busy_timeout = 30000` — concurrent `BEGIN IMMEDIATE` queue safely.
* `synchronous = NORMAL` — fast enough for laptops; durable enough for ops.

Pass `Agent(store=store, session_id=sess.id, autosave=True)` and every
turn (user, assistant, tool) is auto-persisted.

## PostgresSessionStore

For multi-host deploys, swap the SQLite store for the Postgres adapter:

```python
from agentic_engine.core.postgres import PostgresSessionStore

store = PostgresSessionStore(dsn="postgres://user:pass@host:5432/agentic")
```

Same surface (`upsert_project`, `start_session`, `append`, `messages`).
Requires the `[postgres]` extra (`psycopg[binary]`).

## Cron with retry + DLQ

```python
from agentic_engine import CronManager

mgr = CronManager()
mgr.add(
    name="nightly-summary",
    schedule={"kind": "cron", "expr": "0 2 * * *", "tz": "Asia/Singapore"},
    payload={"type": "agent_turn", "message": "Summarise yesterday."},
    max_retries=3, retry_backoff_s=15,
)
```

* **Retries** with exponential backoff (`retry_backoff_s` × 2^n).
* **Dead-letter queue** at `~/.agentic-engine/cron.dlq.jsonl` when
  retries are exhausted.
* **Run history** via `mgr.runs(job_id, limit=20)` — handy for
  building dashboards.
