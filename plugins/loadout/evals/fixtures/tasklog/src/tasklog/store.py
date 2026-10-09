"""SQLite-backed task storage."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

MAX_TITLE_LEN = 120


@dataclass
class Task:
    id: int
    title: str
    created: float
    archived: bool = False


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT, created REAL, archived INTEGER DEFAULT 0)"
        )

    def add(self, title: str) -> Task:
        if not title.strip():
            raise ValueError("title must not be empty")
        if len(title) > MAX_TITLE_LEN:
            raise ValueError(f"title longer than {MAX_TITLE_LEN} characters")
        now = time.time()
        cur = self.db.execute("INSERT INTO tasks (title, created) VALUES (?, ?)", (title, now))
        self.db.commit()
        return Task(cur.lastrowid, title, now)

    def list(self, include_archived: bool = False) -> list[Task]:
        sql = "SELECT id, title, created, archived FROM tasks"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY created DESC"
        return [Task(r[0], r[1], r[2], bool(r[3])) for r in self.db.execute(sql)]

    def archive(self, task_id: int) -> None:
        self.db.execute("UPDATE tasks SET archived = 1 WHERE id = ?", (task_id,))
        self.db.commit()
