from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

SCHEMA = """CREATE TABLE IF NOT EXISTS scheduled_tasks(
    id INTEGER PRIMARY KEY, conversation_id TEXT, kind TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL,
    run_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL)"""

_NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10, "fifteen": 15,
              "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "half": 30}


def parse_when(text: str, now: datetime | None = None) -> datetime:
    """Understands: "in 30 minutes", "in 2 hours", "in half an hour", "at 6 pm", "6:30pm", "tomorrow at 9",
    "tomorrow morning", "tonight at 9", "18:00", "2026-11-09 18:00". Raises ValueError otherwise."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    t = (text or "").strip().casefold()
    if not t or t in ("now", "right now", "immediately"):
        raise ValueError("No time given.")
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[ t](\d{1,2}):(\d{2})", t)
    if m:
        return datetime.fromisoformat(f"{m.group(1)} {int(m.group(2)):02d}:{m.group(3)}")
    if t in ("in half an hour", "in half hour"):
        return now + timedelta(minutes=30)
    m = re.fullmatch(r"(?:in|after)\s+([\w-]+)\s*(minutes?|mins?|hours?|hrs?)", t)
    if m:
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw)
        if not n:
            raise ValueError(f"Couldn't understand '{text}'.")
        return now + (timedelta(hours=n) if m.group(2).startswith(("h",)) else timedelta(minutes=n))
    day = 0
    if "tomorrow" in t:
        day = 1
    t = re.sub(r"\b(today|tomorrow|at|on)\b", " ", t)
    default_hour = {"morning": 9, "afternoon": 14, "evening": 18, "tonight": 21, "night": 21}
    part = next((p for p in default_hour if re.search(rf"\b{p}\b", t)), None)
    t = re.sub(r"\b(morning|afternoon|evening|tonight|night)\b", " ", t).strip()
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", t) if t else None
    if not m and part:
        hour, minute = default_hour[part], 0
    elif m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(".", "")
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        elif not ampm and part in ("evening", "tonight", "night", "afternoon") and hour < 12:
            hour += 12
        if hour > 23 or minute > 59:
            raise ValueError(f"'{text}' isn't a valid time.")
    else:
        raise ValueError(f"Couldn't understand the time '{text}'. Try 'at 6 pm' or 'in 30 minutes'.")
    when = now.replace(hour=hour, minute=minute) + timedelta(days=day)
    if when <= now:
        when += timedelta(days=1)
    return when


class Scheduler:
    def __init__(self, db):
        self.db = db
        db._run(SCHEMA)

    def add(self, kind: str, title: str, payload: dict, run_at: datetime, conversation_id: str = "") -> int:
        self.db._run("INSERT INTO scheduled_tasks(conversation_id,kind,title,payload,run_at,created_at) VALUES(?,?,?,?,?,?)",
                     (conversation_id, kind, title, json.dumps(payload), run_at.isoformat(timespec="minutes"),
                      datetime.now().isoformat(timespec="seconds")))
        return self.db._run("SELECT max(id) AS id FROM scheduled_tasks")[0]["id"]

    def pending(self) -> list[dict]:
        return self.db._run("SELECT * FROM scheduled_tasks WHERE status='pending' ORDER BY run_at")

    def due(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now()
        return [t for t in self.pending() if datetime.fromisoformat(t["run_at"]) <= now]

    def finish(self, task_id: int, status: str = "done") -> None:
        self.db._run("UPDATE scheduled_tasks SET status=? WHERE id=?", (status, task_id))

    def cancel(self, task_id: int) -> bool:
        rows = self.db._run("SELECT id FROM scheduled_tasks WHERE id=? AND status='pending'", (task_id,))
        if rows:
            self.finish(task_id, "cancelled")
        return bool(rows)
