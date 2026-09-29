from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class MemoryHit:
    kind: str
    source: str
    title: str
    content: str
    score: float

class MemoryStore:
    """Persistent SQLite memory + FTS5 document retrieval."""

    def __init__(self, path: str | Path = "data/jenefar_memory.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                kind UNINDEXED,
                source UNINDEXED,
                title,
                content,
                ref_id UNINDEXED
            );
            """)

    def remember_message(self, session_id: str, role: str, content: str) -> None:
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            ref_id = str(cur.lastrowid)
            con.execute(
                "INSERT INTO memory_fts(kind, source, title, content, ref_id) VALUES (?, ?, ?, ?, ?)",
                ("message", session_id, role, content, ref_id),
            )

    def add_document(self, *, source: str, title: str, content: str) -> bool:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._connect() as con:
            try:
                cur = con.execute(
                    "INSERT INTO documents(source, title, content, content_hash) VALUES (?, ?, ?, ?)",
                    (source, title, content, digest),
                )
            except sqlite3.IntegrityError:
                return False
            con.execute(
                "INSERT INTO memory_fts(kind, source, title, content, ref_id) VALUES (?, ?, ?, ?, ?)",
                ("document", source, title, content, str(cur.lastrowid)),
            )
        return True

    def search(self, query: str, *, limit: int = 8) -> list[MemoryHit]:
        q = " ".join(query.split()).strip()
        if not q:
            return []

        # FTS5 MATCH syntax can fail on punctuation-heavy natural language.
        tokens = [token for token in q.replace('"', " ").split() if token]
        match_query = " OR ".join(f'"{token}"' for token in tokens[:12])
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT kind, source, title, content,
                       bm25(memory_fts) AS rank
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match_query, limit),
            ).fetchall()

        return [
            MemoryHit(
                kind=row["kind"],
                source=row["source"],
                title=row["title"],
                content=row["content"],
                score=float(row["rank"]),
            )
            for row in rows
        ]

    def recent_messages(self, session_id: str, *, limit: int = 20) -> list[dict[str, str]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]
