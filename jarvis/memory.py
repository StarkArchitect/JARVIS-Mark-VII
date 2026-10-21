"""SQLite-backed memory: durable facts + rolling conversation turns."""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'task',
    status TEXT NOT NULL DEFAULT 'pending',
    due_time TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    completed_at REAL
);
"""


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class Memory:
    """Persistent memory in SQLite (WAL mode). Tables: facts, turns."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent / "data" / "jarvis.db"
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ facts

    def add_fact(self, fact: str, tags: str = "") -> None:
        self._conn.execute(
            "INSERT INTO facts (fact, tags, created_at) VALUES (?, ?, ?)",
            (fact.strip(), tags.strip(), time.time()),
        )
        self._conn.commit()

    def search(self, query: str, k: int = 5) -> list[str]:
        """Top-k facts by keyword overlap (no embeddings)."""
        rows = self._conn.execute("SELECT fact, tags, created_at FROM facts").fetchall()
        q_tokens = _tokens(query)
        scored: list[tuple[float, float, str]] = []
        for row in rows:
            fact_text = f"{row['fact']} {row['tags']}".lower()
            f_tokens = _tokens(fact_text)
            overlap = len(q_tokens & f_tokens)
            substring_boost = sum(1 for t in q_tokens if len(t) >= 3 and t in fact_text)
            score = overlap * 2 + substring_boost
            if score > 0:
                scored.append((score, row["created_at"], row["fact"]))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        return [fact for _, _, fact in scored[:k]]

    def all_facts(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT fact, tags FROM facts ORDER BY created_at DESC"
        ).fetchall()
        return [f"{row['fact']}" + (f"  [{row['tags']}]" if row["tags"] else "") for row in rows]

    # ------------------------------------------------------------------ turns

    def add_turn(self, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO turns (role, content, created_at) VALUES (?, ?, ?)",
            (role, content.strip(), time.time()),
        )
        self._conn.commit()

    def recent(self, n: int) -> list[dict]:
        """Most recent *n* turns in chronological order (oldest first)."""
        rows = self._conn.execute(
            "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def count_turns(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM turns").fetchone()
        return int(row["c"])

    # Alias for safety
    append = add_turn

    # ------------------------------------------------------------------ plans & agenda

    def add_plan(self, title: str, category: str = "task", due_time: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO plans (title, category, status, due_time, created_at) VALUES (?, ?, 'pending', ?, ?)",
            (title.strip(), category.strip(), due_time.strip(), time.time()),
        )
        self._conn.commit()
        return cur.lastrowid or 0

    def list_plans(self, status: str = "pending") -> list[dict]:
        if status == "all":
            rows = self._conn.execute(
                "SELECT id, title, category, status, due_time, created_at, completed_at FROM plans ORDER BY id ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, category, status, due_time, created_at, completed_at FROM plans WHERE status = ? ORDER BY id ASC",
                (status,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "category": r["category"],
                "status": r["status"],
                "due_time": r["due_time"],
                "created_at": r["created_at"],
                "completed_at": r["completed_at"],
            }
            for r in rows
        ]

    def complete_plan(self, item_id_or_title: str | int) -> bool:
        if isinstance(item_id_or_title, int) or (isinstance(item_id_or_title, str) and item_id_or_title.isdigit()):
            pid = int(item_id_or_title)
            cur = self._conn.execute(
                "UPDATE plans SET status = 'completed', completed_at = ? WHERE id = ?",
                (time.time(), pid),
            )
        else:
            cur = self._conn.execute(
                "UPDATE plans SET status = 'completed', completed_at = ? WHERE title LIKE ?",
                (time.time(), f"%{item_id_or_title.strip()}%"),
            )
        self._conn.commit()
        return cur.rowcount > 0

    def clear_completed_plans(self) -> int:
        cur = self._conn.execute("DELETE FROM plans WHERE status = 'completed'")
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------ clear

    def clear(self) -> None:
        self._conn.execute("DELETE FROM facts")
        self._conn.execute("DELETE FROM turns")
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
