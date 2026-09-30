from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jenefar.memory.semantic import SemanticEmbedder
from jenefar.memory.store import MemoryHit, MemoryStore


@dataclass(frozen=True)
class AdvancedMemoryHit:
    id: int
    layer: str
    kind: str
    source: str
    title: str
    content: str
    score: float
    importance: float
    access_count: int
    created_at: str


@dataclass(frozen=True)
class MemoryRecall:
    hits: tuple[AdvancedMemoryHit, ...]
    procedures: tuple[dict[str, Any], ...] = ()


class AdvancedMemory:
    """Layered episodic/semantic/procedural memory with fused retrieval.

    Retrieval combines lexical FTS, optional local embeddings, importance and
    time decay. Everything is local SQLite; remote model calls are not required.
    """

    HALF_LIFE_DAYS = {
        "episodic": 30.0,
        "semantic": 120.0,
        "procedural": 365.0,
    }

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        path: str | Path | None = None,
        embedder: SemanticEmbedder | None = None,
    ) -> None:
        self.store = store or MemoryStore(path or "data/jenefar_memory.db")
        self.path = self.store.path
        self.embedder = embedder or SemanticEmbedder()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    layer TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    session_id TEXT,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    ttl_seconds REAL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    embedding TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_memory_items_layer
                    ON memory_items(layer);
                CREATE INDEX IF NOT EXISTS idx_memory_items_session
                    ON memory_items(session_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
                    title,
                    content,
                    layer UNINDEXED,
                    kind UNINDEXED,
                    source UNINDEXED,
                    item_id UNINDEXED
                );

                CREATE TABLE IF NOT EXISTS procedures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    trigger_text TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    constraints_json TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL DEFAULT 'user',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                );

                CREATE TABLE IF NOT EXISTS memory_access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    accessed_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @classmethod
    def _decay(cls, layer: str, created_at: str, now: datetime) -> float:
        try:
            age_days = max(
                0.0,
                (now - cls._parse_time(created_at)).total_seconds() / 86400.0,
            )
        except (TypeError, ValueError):
            age_days = 0.0
        half_life = cls.HALF_LIFE_DAYS.get(layer, 60.0)
        return 0.5 ** (age_days / half_life)

    def _store_item(
        self,
        *,
        layer: str,
        kind: str,
        title: str,
        content: str,
        source: str,
        session_id: str | None,
        importance: float,
        tags: Iterable[str],
        ttl_seconds: float | None,
    ) -> AdvancedMemoryHit | None:
        layer = str(layer).strip().lower()
        kind = str(kind).strip().lower()
        title = " ".join(str(title).split()).strip()
        content = str(content).strip()
        source = " ".join(str(source).split()).strip()
        if layer not in {"episodic", "semantic", "procedural"}:
            raise ValueError("layer must be episodic, semantic or procedural")
        if not title or not content or not source:
            raise ValueError("title, content and source are required")

        clean_tags = sorted(
            {str(tag).strip().lower() for tag in tags if str(tag).strip()}
        )[:30]
        now = self._now().isoformat()
        digest = hashlib.sha256(
            f"{layer}\n{kind}\n{source}\n{title}\n{content}".encode("utf-8")
        ).hexdigest()
        embedding = self.embedder.encode(content)
        encoded_embedding = json.dumps(embedding) if embedding else None

        with self._connect() as con:
            try:
                cur = con.execute(
                    """
                    INSERT INTO memory_items(
                        layer, kind, session_id, source, title, content, content_hash,
                        importance, created_at, accessed_at, access_count,
                        ttl_seconds, tags_json, embedding
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        layer,
                        kind,
                        session_id,
                        source,
                        title,
                        content,
                        digest,
                        max(0.0, min(1.0, float(importance))),
                        now,
                        now,
                        ttl_seconds,
                        json.dumps(clean_tags, ensure_ascii=False),
                        encoded_embedding,
                    ),
                )
            except sqlite3.IntegrityError:
                row = con.execute(
                    """
                    SELECT id, layer, kind, source, title, content, importance,
                           access_count, created_at
                    FROM memory_items WHERE content_hash = ?
                    """,
                    (digest,),
                ).fetchone()
                return self._row_to_hit(row, 0.0) if row else None

            item_id = int(cur.lastrowid)
            con.execute(
                """
                INSERT INTO memory_items_fts(rowid, title, content, layer, kind, source, item_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, title, content, layer, kind, source, str(item_id)),
            )
            row = con.execute(
                """
                SELECT id, layer, kind, source, title, content, importance,
                       access_count, created_at
                FROM memory_items WHERE id = ?
                """,
                (item_id,),
            ).fetchone()

        return self._row_to_hit(row, 1.0)

    @staticmethod
    def _row_to_hit(row: sqlite3.Row | None, score: float) -> AdvancedMemoryHit:
        if row is None:
            raise ValueError("Memory row was not found.")
        return AdvancedMemoryHit(
            id=int(row["id"]),
            layer=str(row["layer"]),
            kind=str(row["kind"]),
            source=str(row["source"]),
            title=str(row["title"]),
            content=str(row["content"]),
            score=float(score),
            importance=float(row["importance"]),
            access_count=int(row["access_count"]),
            created_at=str(row["created_at"]),
        )

    def record_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        importance: float = 0.45,
    ) -> None:
        self.store.remember_message(session_id, role, content)
        self._store_item(
            layer="episodic",
            kind="message",
            title=f"{role} message",
            content=content,
            source="conversation",
            session_id=session_id,
            importance=importance,
            tags=(role, "conversation"),
            ttl_seconds=None,
        )

    def record_episode(
        self,
        *,
        title: str,
        content: str,
        source: str = "conversation",
        session_id: str | None = None,
        importance: float = 0.65,
        tags: Iterable[str] = (),
        ttl_seconds: float | None = None,
    ) -> None:
        self._store_item(
            layer="episodic",
            kind="episode",
            title=title,
            content=content,
            source=source,
            session_id=session_id,
            importance=importance,
            tags=tags,
            ttl_seconds=ttl_seconds,
        )

    def remember_fact(
        self,
        *,
        title: str,
        content: str,
        source: str = "user",
        importance: float = 0.8,
        tags: Iterable[str] = (),
    ) -> None:
        self._store_item(
            layer="semantic",
            kind="fact",
            title=title,
            content=content,
            source=source,
            session_id=None,
            importance=importance,
            tags=tags,
            ttl_seconds=None,
        )

    def save_procedure(
        self,
        *,
        name: str,
        trigger_text: str,
        steps: list[str],
        constraints: list[str] | None = None,
        source: str = "user",
        importance: float = 0.9,
    ) -> None:
        clean_name = " ".join(str(name).split()).strip().lower()
        clean_trigger = " ".join(str(trigger_text).split()).strip()
        clean_steps = [" ".join(str(x).split()).strip() for x in steps if str(x).strip()]
        clean_constraints = [
            " ".join(str(x).split()).strip()
            for x in (constraints or [])
            if str(x).strip()
        ]
        if not clean_name or not clean_trigger or not clean_steps:
            raise ValueError("procedure name, trigger_text and steps are required")

        now = self._now().isoformat()
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO procedures(
                    name, trigger_text, steps_json, constraints_json, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    trigger_text=excluded.trigger_text,
                    steps_json=excluded.steps_json,
                    constraints_json=excluded.constraints_json,
                    source=excluded.source
                """,
                (
                    clean_name,
                    clean_trigger,
                    json.dumps(clean_steps, ensure_ascii=False),
                    json.dumps(clean_constraints, ensure_ascii=False),
                    source,
                    now,
                ),
            )
        self._store_item(
            layer="procedural",
            kind="procedure",
            title=clean_name,
            content=" -> ".join(clean_steps),
            source=source,
            session_id=None,
            importance=importance,
            tags=("procedure", clean_name),
            ttl_seconds=None,
        )

    def find_procedures(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        tokens = [token for token in " ".join(query.split()).lower().split() if token]
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT id, name, trigger_text, steps_json, constraints_json,
                       source, use_count, success_count, created_at, last_used_at
                FROM procedures
                ORDER BY use_count DESC, id DESC
                LIMIT 100
                """
            ).fetchall()
        ranked: list[tuple[float, sqlite3.Row]] = []
        normalized = " ".join(tokens)
        for row in rows:
            haystack = f"{row['name']} {row['trigger_text']}".lower()
            lexical = sum(1 for token in tokens if token in haystack)
            exact = 1.0 if normalized and normalized in haystack else 0.0
            ranked.append((exact * 2.0 + lexical, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        output = []
        for _score, row in ranked[: max(1, int(limit))]:
            output.append({
                "id": int(row["id"]),
                "name": row["name"],
                "trigger_text": row["trigger_text"],
                "steps": json.loads(row["steps_json"]),
                "constraints": json.loads(row["constraints_json"]),
                "source": row["source"],
                "use_count": int(row["use_count"]),
                "success_count": int(row["success_count"]),
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
            })
        return output

    def mark_procedure_use(self, name: str, *, success: bool = True) -> None:
        now = self._now().isoformat()
        with self._connect() as con:
            con.execute(
                """
                UPDATE procedures
                SET use_count = use_count + 1,
                    success_count = success_count + ?,
                    last_used_at = ?
                WHERE name = ?
                """,
                (1 if success else 0, now, str(name).strip().lower()),
            )

    def _fts_candidates(self, query: str, limit: int) -> list[tuple[sqlite3.Row, float]]:
        tokens = [token.replace('"', " ") for token in " ".join(query.split()).split() if token]
        if not tokens:
            return []
        match_query = " OR ".join(f'"{token}"' for token in tokens[:16])
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT m.id, m.layer, m.kind, m.source, m.title, m.content,
                       m.importance, m.access_count, m.created_at, m.embedding,
                       bm25(memory_items_fts) AS bm
                FROM memory_items_fts f
                JOIN memory_items m ON m.id = CAST(f.item_id AS INTEGER)
                WHERE memory_items_fts MATCH ?
                ORDER BY bm
                LIMIT ?
                """,
                (match_query, max(20, limit * 5)),
            ).fetchall()
        return [(row, 1.0 / (1.0 + abs(float(row["bm"])))) for row in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        layers: Iterable[str] | None = None,
    ) -> list[AdvancedMemoryHit]:
        normalized = " ".join(str(query).split()).strip()
        if not normalized:
            return []
        allowed_layers = {str(item).strip().lower() for item in (layers or []) if str(item).strip()}
        now = self._now()
        query_embedding = self.embedder.encode(normalized)
        lexical_rows = self._fts_candidates(normalized, max(limit * 5, 20))

        candidates: dict[int, tuple[sqlite3.Row, float]] = {
            int(row["id"]): (row, lexical) for row, lexical in lexical_rows
        }

        if query_embedding:
            with self._connect() as con:
                rows = con.execute(
                    """
                    SELECT id, layer, kind, source, title, content, importance,
                           access_count, created_at, embedding
                    FROM memory_items
                    """
                ).fetchall()
            for row in rows:
                if not row["embedding"]:
                    continue
                try:
                    semantic = self.embedder.cosine(
                        query_embedding,
                        json.loads(row["embedding"]),
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                existing = candidates.get(int(row["id"]))
                lexical = existing[1] if existing else 0.0
                candidates[int(row["id"])] = (row, max(semantic, 0.0) if existing is None else lexical)

        scored: list[tuple[float, sqlite3.Row]] = []
        for row, lexical in candidates.values():
            layer = str(row["layer"])
            if allowed_layers and layer not in allowed_layers:
                continue
            decay = self._decay(layer, str(row["created_at"]), now)
            importance = float(row["importance"])
            access_bonus = min(0.08, int(row["access_count"]) * 0.01)
            semantic = 0.0
            if query_embedding and row["embedding"]:
                try:
                    semantic = max(
                        0.0,
                        self.embedder.cosine(query_embedding, json.loads(row["embedding"])),
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    semantic = 0.0
            score = (
                0.52 * lexical
                + 0.25 * semantic
                + 0.15 * importance * decay
                + access_bonus
            )
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        output: list[AdvancedMemoryHit] = []
        with self._connect() as con:
            for score, row in scored[: max(1, int(limit))]:
                con.execute(
                    """
                    UPDATE memory_items
                    SET accessed_at = ?, access_count = access_count + 1
                    WHERE id = ?
                    """,
                    (now.isoformat(), int(row["id"])),
                )
                con.execute(
                    "INSERT INTO memory_access_log(item_id, accessed_at) VALUES (?, ?)",
                    (int(row["id"]), now.isoformat()),
                )
                output.append(self._row_to_hit(row, score))
        return output

    def recall(
        self,
        query: str,
        *,
        limit: int = 8,
        include_procedures: bool = True,
    ) -> MemoryRecall:
        hits = self.search(query, limit=limit)
        procedures = (
            tuple(self.find_procedures(query, limit=min(5, limit)))
            if include_procedures
            else ()
        )
        return MemoryRecall(tuple(hits), procedures)

    def consolidate_messages(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        *,
        title: str | None = None,
        importance: float = 0.72,
    ) -> None:
        clean = [
            f"{item.get('role', 'unknown')}: {item.get('content', '').strip()}"
            for item in messages
            if str(item.get("content", "")).strip()
        ]
        if not clean:
            return
        self.record_episode(
            title=title or f"Session {session_id} episode",
            content="\n".join(clean[-20:])[:12000],
            source="session_consolidation",
            session_id=session_id,
            importance=importance,
            tags=("session", "consolidated"),
        )

    def purge_expired(self) -> int:
        now = time.time()
        removed = 0
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, ttl_seconds, created_at FROM memory_items WHERE ttl_seconds IS NOT NULL"
            ).fetchall()
            for row in rows:
                try:
                    created = self._parse_time(str(row["created_at"])).timestamp()
                except (TypeError, ValueError):
                    continue
                if created + float(row["ttl_seconds"]) <= now:
                    con.execute("DELETE FROM memory_items WHERE id = ?", (int(row["id"]),))
                    con.execute("DELETE FROM memory_items_fts WHERE rowid = ?", (int(row["id"]),))
                    removed += 1
        return removed


__all__ = ["AdvancedMemory", "AdvancedMemoryHit", "MemoryRecall"]
