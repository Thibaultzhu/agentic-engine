"""Postgres / DSN abstraction layer — opt-in.

The default :class:`agentic_engine.core.sessions.SessionStore` is sqlite-only.
For multi-process / multi-host deployments you can switch to Postgres by
setting ``AGENTIC_DB_URL=postgresql://user:pass@host/db`` and constructing
:class:`PostgresSessionStore` instead.

Implementation is **schema-compatible** with the sqlite store and depends on
``psycopg`` (v3) which is *not* a hard requirement of the package — the class
imports lazily so unit tests on machines without psycopg still pass.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .sessions import Message, Project, Session  # reuse dataclasses

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    root TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);
"""


class PostgresSessionStore:
    """Drop-in alternative to SessionStore backed by Postgres."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get("AGENTIC_DB_URL", "")
        if not self.dsn:
            raise RuntimeError("PostgresSessionStore requires AGENTIC_DB_URL or dsn=")
        self._psycopg = self._lazy_psycopg()
        with self._cx() as cx:
            cur = cx.cursor()
            cur.execute(_SCHEMA)

    @staticmethod
    def _lazy_psycopg() -> Any:  # pragma: no cover — env-dependent
        try:
            import psycopg

            return psycopg
        except ImportError as e:
            raise RuntimeError("psycopg (v3) not installed; pip install 'psycopg[binary]'") from e

    @contextmanager
    def _cx(self) -> Iterator[Any]:
        cx = self._psycopg.connect(self.dsn, autocommit=False)
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise
        finally:
            cx.close()

    # ---------- projects ----------
    def upsert_project(self, name: str, root: str) -> Project:  # pragma: no cover — env
        now = _dt.datetime.now().isoformat(timespec="seconds")
        pid = uuid.uuid4().hex[:12]
        with self._cx() as cx:
            cur = cx.cursor()
            cur.execute("SELECT id, name, root, created_at FROM projects WHERE name=%s", (name,))
            row = cur.fetchone()
            if row:
                return Project(id=row[0], name=row[1], root=row[2], created_at=row[3])
            cur.execute(
                "INSERT INTO projects(id,name,root,created_at) VALUES(%s,%s,%s,%s)",
                (pid, name, root, now),
            )
        return Project(id=pid, name=name, root=root, created_at=now)

    def new_session(self, project_id: str, title: str = "untitled") -> Session:  # pragma: no cover
        now = _dt.datetime.now().isoformat(timespec="seconds")
        sid = uuid.uuid4().hex[:12]
        with self._cx() as cx:
            cur = cx.cursor()
            cur.execute(
                "INSERT INTO sessions(id,project_id,title,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s)",
                (sid, project_id, title, now, now),
            )
        return Session(id=sid, project_id=project_id, title=title,
                       created_at=now, updated_at=now, archived=False)

    def append(self, session_id: str, role: str, content: str,
               tool_calls: list[dict[str, Any]] | None = None) -> Message:  # pragma: no cover
        now = _dt.datetime.now().isoformat(timespec="seconds")
        with self._cx() as cx:
            cur = cx.cursor()
            cur.execute(
                "INSERT INTO messages(session_id,role,content,tool_calls_json,created_at) "
                "VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (session_id, role, content, json.dumps(tool_calls) if tool_calls else None, now),
            )
            mid = cur.fetchone()[0]
            cur.execute("UPDATE sessions SET updated_at=%s WHERE id=%s", (now, session_id))
        return Message(id=mid, session_id=session_id, role=role, content=content,
                       tool_calls=tool_calls, created_at=now)


__all__ = ["PostgresSessionStore"]
