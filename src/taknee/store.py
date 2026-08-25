"""SQLite store: tasks, spans, events, approvals.

Everything the system does is appended here (WAL mode) so that:
  - the Traces view works live AND after completion from the same tables,
  - a crash leaves a consistent prefix -> exact resume,
  - governors (cost/time/steps) are data-driven and auditable.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def _locked(fn: F) -> F:
    """Serialize store access — the orchestrator runs on a worker thread."""

    @wraps(fn)
    def wrapper(self: Store, *args: Any, **kwargs: Any):
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',   -- created|running|awaiting_approval|done|failed|stopped
    stage TEXT NOT NULL DEFAULT 'start',      -- current state-machine stage
    usd REAL NOT NULL DEFAULT 0,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    error TEXT,
    display_prompt TEXT,
    thread_id TEXT,
    parent_task_id TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    parent_id INTEGER,
    kind TEXT NOT NULL,          -- stage|llm|tool|approval|compaction
    name TEXT NOT NULL,
    model TEXT,
    provider TEXT,
    route_reason TEXT,
    input_json TEXT,
    output_json TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    usd REAL DEFAULT 0,
    t_start REAL,
    t_end REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    ts REAL NOT NULL,
    type TEXT NOT NULL,          -- status|route|cap|compaction|approval|note
    payload_json TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL,          -- patch|command
    payload_json TEXT NOT NULL,  -- hunks or command line
    decision TEXT,               -- pending|accepted|rejected|partial
    rejected_json TEXT,
    created_at REAL NOT NULL,
    decided_at REAL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spans_task ON spans(task_id);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id);
"""


def _now() -> float:
    return time.time()


def new_task_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # orchestrator threads share this connection with the FastAPI thread
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(tasks)").fetchall()}
        for name, kind in (
            ("display_prompt", "TEXT"), ("thread_id", "TEXT"), ("parent_task_id", "TEXT")
        ):
            if name not in cols:
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {kind}")
        self.conn.execute("UPDATE tasks SET display_prompt=prompt WHERE display_prompt IS NULL")
        self.conn.execute("UPDATE tasks SET thread_id=id WHERE thread_id IS NULL")

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    # -- tasks -----------------------------------------------------------

    @_locked
    def create_task(
        self, prompt: str, workspace: str, *, display_prompt: str | None = None,
        thread_id: str | None = None, parent_task_id: str | None = None,
    ) -> str:
        tid = new_task_id()
        now = _now()
        self.conn.execute(
            "INSERT INTO tasks (id, prompt, workspace, status, stage, created_at, updated_at, display_prompt, thread_id, parent_task_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tid, prompt, workspace, "created", "start", now, now, display_prompt or prompt, thread_id or tid, parent_task_id),
        )
        self.add_event(tid, "status", {"status": "created"})
        return tid

    @_locked
    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    @_locked
    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    @_locked
    def update_task(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE tasks SET {cols} WHERE id=?", (*fields.values(), task_id))
        self.conn.commit()

    @_locked
    def add_usage(self, task_id: str, tokens_in: int, tokens_out: int, usd: float) -> None:
        self.conn.execute(
            "UPDATE tasks SET tokens_in=tokens_in+?, tokens_out=tokens_out+?, usd=usd+?,"
            " updated_at=? WHERE id=?",
            (tokens_in, tokens_out, usd, _now(), task_id),
        )
        self.conn.commit()

    # -- spans -----------------------------------------------------------

    @_locked
    def add_span(
        self,
        task_id: str,
        kind: str,
        name: str,
        parent_id: int | None = None,
        model: str | None = None,
        provider: str | None = None,
        route_reason: str | None = None,
        input_data: Any = None,
        output_data: Any = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        usd: float = 0.0,
        t_start: float | None = None,
        t_end: float | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO spans (task_id,parent_id,kind,name,model,provider,route_reason,"
            "input_json,output_json,tokens_in,tokens_out,usd,t_start,t_end)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                parent_id,
                kind,
                name,
                model,
                provider,
                route_reason,
                _json(input_data),
                _json(output_data),
                tokens_in,
                tokens_out,
                usd,
                t_start if t_start is not None else _now(),
                t_end if t_end is not None else _now(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    @_locked
    def end_span(self, span_id: int, output_data: Any = None, **usage: Any) -> None:
        sets = {"t_end": _now()}
        if output_data is not None:
            sets["output_json"] = _json(output_data)
        for k in ("tokens_in", "tokens_out", "usd"):
            if k in usage:
                sets[k] = usage[k]
        cols = ", ".join(f"{k}=?" for k in sets)
        self.conn.execute(f"UPDATE spans SET {cols} WHERE id=?", (*sets.values(), span_id))
        self.conn.commit()

    @_locked
    def spans_for_task(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM spans WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()
        return [_decode(r) for r in rows]

    # -- events ----------------------------------------------------------

    @_locked
    def add_event(self, task_id: str, type_: str, payload: Any = None) -> None:
        self.conn.execute(
            "INSERT INTO events (task_id, ts, type, payload_json) VALUES (?,?,?,?)",
            (task_id, _now(), type_, _json(payload)),
        )
        self.conn.commit()

    @_locked
    def events_for_task(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()
        return [_decode(r) for r in rows]

    @_locked
    def add_message(self, task_id: str, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO messages (task_id, role, content, ts) VALUES (?,?,?,?)",
            (task_id, role, content, _now()),
        )
        self.conn.commit()

    @_locked
    def messages_for_task(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    @_locked
    def messages_for_thread(self, task_id: str) -> list[dict[str, Any]]:
        task = self.conn.execute("SELECT thread_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            return []
        rows = self.conn.execute(
            "SELECT m.* FROM messages m JOIN tasks t ON t.id=m.task_id "
            "WHERE t.thread_id=? ORDER BY m.id", (task["thread_id"],)
        ).fetchall()
        return [dict(r) for r in rows]

    # -- approvals ---------------------------------------------------------

    @_locked
    def add_approval(self, task_id: str, kind: str, payload: Any) -> int:
        cur = self.conn.execute(
            "INSERT INTO approvals (task_id, kind, payload_json, decision, created_at)"
            " VALUES (?,?,?, 'pending', ?)",
            (task_id, kind, _json(payload), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    @_locked
    def get_approval(self, approval_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
        return _decode(row) if row else None

    @_locked
    def pending_approvals(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE decision='pending' ORDER BY id DESC"
        ).fetchall()
        return [_decode(r) for r in rows]

    @_locked
    def resolve_approval(
        self, approval_id: int, decision: str, rejected: Any = None
    ) -> None:
        self.conn.execute(
            "UPDATE approvals SET decision=?, rejected_json=?, decided_at=? WHERE id=?",
            (decision, _json(rejected), _now(), approval_id),
        )
        self.conn.commit()


def _json(v: Any) -> str | None:
    return json.dumps(v) if v is not None else None


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for k in ("input_json", "output_json", "payload_json", "rejected_json"):
        if d.get(k) is not None:
            try:
                d[k.replace("_json", "") if k != "rejected_json" else "rejected"] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d
