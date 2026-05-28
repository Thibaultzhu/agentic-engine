# Postgres adapter

For multi-host deployments, replace the SQLite store with
`PostgresSessionStore`:

```python
from agentic_engine.core.postgres import PostgresSessionStore

store = PostgresSessionStore(dsn="postgres://user:pass@host:5432/agentic")
proj = store.upsert_project("agentic", "/var/agentic")
sess = store.start_session(proj.id, name="prod")
store.append(sess.id, role="user", content="hi")
```

## Install

```bash
pip install "agentic-engine[postgres]"
# or
pip install psycopg[binary] >= 3.2
```

The dependency is **lazy-imported** — your install does not pull
`psycopg` unless you actually call `PostgresSessionStore(...)`.

## Schema

The first call against a fresh DB executes the same DDL bundled into
SQLite (`projects`, `sessions`, `messages`) plus a small `agentic_meta`
table that records the schema version. Future migrations bump the
`schema_version` row and apply the diff via plain SQL — no Alembic.

## Connection knobs

* `min_size`, `max_size` (defaults 1, 8) — psycopg connection pool.
* `prepare_threshold` — set to `None` to disable server-side prepared
  statements when the database is `pgbouncer` in transaction mode.

## SQLite ↔ Postgres differences

* Both stores use UPSERT for project rows.
* Postgres uses `INSERT ... ON CONFLICT (id) DO UPDATE`; SQLite uses
  `INSERT ... ON CONFLICT(id) DO UPDATE`.
* `messages.payload_json` is `JSONB` on Postgres, `TEXT` on SQLite —
  the helper transparently `json.dumps` on the way in and
  `json.loads` on the way out.
