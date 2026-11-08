from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations(
    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS action_logs(
    id INTEGER PRIMARY KEY, request TEXT, tool TEXT, arguments TEXT, approval TEXT, status TEXT,
    result TEXT, created_at TEXT NOT NULL);
"""

EXTRA_COLUMNS = {
    "conversations": {"local_only": "INTEGER NOT NULL DEFAULT 0"},
    "messages": {"route": "TEXT NOT NULL DEFAULT 'local'", "provider": "TEXT NOT NULL DEFAULT ''"},
    "action_logs": {"conversation_id": "TEXT"},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = self._conn()
        try:
            with db:
                db.executescript(SCHEMA)
                for table, columns in EXTRA_COLUMNS.items():
                    existing = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
                    for name, decl in columns.items():
                        if name not in existing:
                            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        finally:
            db.close()

    def _conn(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _run(self, sql: str, params=()) -> list[dict]:
        db = self._conn()
        try:
            with db:
                return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()


    def new_conversation(self, title: str = "New chat") -> str:
        ident, ts = str(uuid.uuid4()), now()
        self._run("INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)", (ident, title, ts, ts))
        return ident

    def conversations(self) -> list[dict]:
        return self._run("SELECT * FROM conversations ORDER BY updated_at DESC")

    def conversation(self, ident: str) -> dict | None:
        rows = self._run("SELECT * FROM conversations WHERE id=?", (ident,))
        return rows[0] if rows else None

    def mark_local_only(self, ident: str) -> None:
        self._run("UPDATE conversations SET local_only=1 WHERE id=?", (ident,))

    def is_local_only(self, ident: str) -> bool:
        row = self.conversation(ident)
        return bool(row and row["local_only"])

    def delete_conversation(self, ident: str) -> None:
        self._run("DELETE FROM messages WHERE conversation_id=?", (ident,))
        self._run("DELETE FROM conversations WHERE id=?", (ident,))


    def add_message(self, conversation_id: str, role: str, content: str, route: str = "local", provider: str = "") -> None:
        ts = now()
        self._run("INSERT INTO messages(conversation_id,role,content,created_at,route,provider) VALUES(?,?,?,?,?,?)",
                  (conversation_id, role, content, ts, route, provider))
        self._run("UPDATE conversations SET updated_at=? WHERE id=?", (ts, conversation_id))
        if role == "user":
            title = " ".join(content.split())[:56]
            self._run("UPDATE conversations SET title=? WHERE id=? AND title='New chat'", (title, conversation_id))

    def messages(self, conversation_id: str) -> list[dict]:
        return self._run("SELECT role,content,route,provider,created_at FROM messages WHERE conversation_id=? ORDER BY id",
                         (conversation_id,))

    def search_conversations(self, text: str) -> list[dict]:
        like = f"%{text}%"
        return self._run("SELECT DISTINCT c.* FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id "
                         "WHERE c.title LIKE ? OR (m.role IN ('user','assistant') AND m.content LIKE ?) "
                         "ORDER BY c.updated_at DESC", (like, like))


    def log_action(self, conversation_id: str, request: str, tool: str, arguments: dict, approval: str,
                   status: str, result) -> None:
        self._run("INSERT INTO action_logs(conversation_id,request,tool,arguments,approval,status,result,created_at) "
                  "VALUES(?,?,?,?,?,?,?,?)",
                  (conversation_id, request, tool, json.dumps(arguments, ensure_ascii=False, default=str),
                   approval, status, str(result)[:4000], now()))

    def action_logs(self, limit: int = 300) -> list[dict]:
        return self._run("SELECT * FROM action_logs ORDER BY id DESC LIMIT ?", (limit,))


    def get(self, key: str, default=None):
        rows = self._run("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set(self, key: str, value) -> None:
        self._run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value)))
