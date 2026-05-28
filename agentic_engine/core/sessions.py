"""Sessions — sqlite-backed multi-project, multi-conversation history.

Schema:
    projects(id, name, root, created_at)
    sessions(id, project_id, title, created_at, updated_at, archived)
    messages(id, session_id, role, content, tool_calls_json, created_at)
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ..config import get_settings


_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    root TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER DEFAULT 0,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);
"""


@dataclass
class Project:
    id: str
    name: str
    root: str
    created_at: str


@dataclass
class Session:
    id: str
    project_id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool


@dataclass
class Message:
    id: int
    session_id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None
    created_at: str


class SessionStore:
    def __init__(self, db_path: Path | None = None):
        s = get_settings()
        self.db_path = db_path or (s.home / "sessions.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._cx() as cx:
            cx.executescript(_SCHEMA)

    @contextmanager
    def _cx(self) -> Iterator[sqlite3.Connection]:
        cx = sqlite3.connect(self.db_path)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys = ON")
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise
        finally:
            cx.close()

    # ---------- projects ----------
    def upsert_project(self, name: str, root: str) -> Project:
        now = _dt.datetime.now().isoformat(timespec="seconds")
        pid = uuid.uuid4().hex[:12]
        with self._cx() as cx:
            row = cx.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
            if row:
                return Project(**dict(row))
            cx.execute(
                "INSERT INTO projects(id,name,root,created_at) VALUES(?,?,?,?)",
                (pid, name, root, now),
            )
        return Project(id=pid, name=name, root=root, created_at=now)

    def list_projects(self) -> list[Project]:
        with self._cx() as cx:
            rows = cx.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [Project(**dict(r)) for r in rows]

    # ---------- sessions ----------
    def new_session(self, project_id: str, title: str = "untitled") -> Session:
        now = _dt.datetime.now().isoformat(timespec="seconds")
        sid = uuid.uuid4().hex[:12]
        with self._cx() as cx:
            cx.execute(
                "INSERT INTO sessions(id,project_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                (sid, project_id, title, now, now),
            )
        return Session(id=sid, project_id=project_id, title=title,
                       created_at=now, updated_at=now, archived=False)

    def list_sessions(self, project_id: str | None = None, archived: bool = False) -> list[Session]:
        q = "SELECT * FROM sessions WHERE archived = ?"
        params: list[Any] = [1 if archived else 0]
        if project_id:
            q += " AND project_id = ?"
            params.append(project_id)
        q += " ORDER BY updated_at DESC"
        with self._cx() as cx:
            rows = cx.execute(q, params).fetchall()
        return [
            Session(
                id=r["id"], project_id=r["project_id"], title=r["title"],
                created_at=r["created_at"], updated_at=r["updated_at"],
                archived=bool(r["archived"]),
            )
            for r in rows
        ]

    def archive(self, session_id: str) -> None:
        with self._cx() as cx:
            cx.execute("UPDATE sessions SET archived=1 WHERE id=?", (session_id,))

    def rename(self, session_id: str, title: str) -> None:
        with self._cx() as cx:
            cx.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))

    # ---------- messages ----------
    def append(self, session_id: str, role: str, content: str,
               tool_calls: list[dict[str, Any]] | None = None) -> Message:
        now = _dt.datetime.now().isoformat(timespec="seconds")
        with self._cx() as cx:
            cur = cx.execute(
                "INSERT INTO messages(session_id,role,content,tool_calls_json,created_at) "
                "VALUES(?,?,?,?,?)",
                (session_id, role, content, json.dumps(tool_calls) if tool_calls else None, now),
            )
            cx.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
            mid = cur.lastrowid
        return Message(id=mid, session_id=session_id, role=role, content=content,
                       tool_calls=tool_calls, created_at=now)

    def history(self, session_id: str, limit: int = 200) -> list[Message]:
        with self._cx() as cx:
            rows = cx.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            tc = json.loads(r["tool_calls_json"]) if r["tool_calls_json"] else None
            out.append(Message(
                id=r["id"], session_id=r["session_id"], role=r["role"],
                content=r["content"], tool_calls=tc, created_at=r["created_at"],
            ))
        return out
