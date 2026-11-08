import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import uuid

class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,conversation_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(id));
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS action_logs(id INTEGER PRIMARY KEY,request TEXT,tool TEXT,arguments TEXT,approval TEXT,status TEXT,result TEXT,created_at TEXT NOT NULL);
            """)
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db
    @staticmethod
    def now(): return datetime.now(timezone.utc).isoformat()
    def new_conversation(self, title="New chat"):
        ident, now = str(uuid.uuid4()), self.now()
        with self.connect() as db: db.execute("INSERT INTO conversations VALUES(?,?,?,?)", (ident,title,now,now))
        return ident
    def conversations(self):
        with self.connect() as db: return [dict(r) for r in db.execute("SELECT * FROM conversations ORDER BY updated_at DESC")]
    def messages(self, ident):
        with self.connect() as db: return [dict(r) for r in db.execute("SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id",(ident,))]
    def add_message(self, ident, role, content):
        now=self.now()
        with self.connect() as db:
            db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",(ident,role,content,now))
            db.execute("UPDATE conversations SET updated_at=? WHERE id=?",(now,ident))
            if role == "user": db.execute("UPDATE conversations SET title=CASE WHEN title='New chat' THEN ? ELSE title END WHERE id=?",(content[:56],ident))
    def log_action(self, request, tool, arguments, approval, status, result):
        import json
        with self.connect() as db: db.execute("INSERT INTO action_logs(request,tool,arguments,approval,status,result,created_at) VALUES(?,?,?,?,?,?,?)",(request,tool,json.dumps(arguments,ensure_ascii=False),approval,status,str(result)[:4000],self.now()))
    def action_logs(self, limit=250):
        with self.connect() as db: return [dict(r) for r in db.execute("SELECT * FROM action_logs ORDER BY id DESC LIMIT ?",(limit,))]
    def get_setting(self,key,default=""):
        with self.connect() as db:
            row=db.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
            return row[0] if row else default
    def set_setting(self,key,value):
        with self.connect() as db: db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value))
