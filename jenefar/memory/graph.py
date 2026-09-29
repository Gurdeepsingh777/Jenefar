from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GraphRelation:
    subject: str
    predicate: str
    object: str


class KnowledgeGraph:
    """SQLite-backed entity/relation graph sharing the Jenefar memory DB."""

    def __init__(self, path: str | Path = "data/jenefar_memory.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    entity_type TEXT NOT NULL DEFAULT 'concept'
                );
                CREATE TABLE IF NOT EXISTS kg_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id INTEGER NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id INTEGER NOT NULL,
                    UNIQUE(subject_id, predicate, object_id),
                    FOREIGN KEY(subject_id) REFERENCES kg_entities(id),
                    FOREIGN KEY(object_id) REFERENCES kg_entities(id)
                );
                """
            )

    def _entity_id(self, con, name: str, entity_type: str = "concept") -> int:
        con.execute(
            "INSERT OR IGNORE INTO kg_entities(name, entity_type) VALUES (?, ?)",
            (name, entity_type),
        )
        row = con.execute("SELECT id FROM kg_entities WHERE name = ?", (name,)).fetchone()
        return int(row["id"])

    def add_relation(self, subject: str, predicate: str, object_: str) -> GraphRelation:
        subject, predicate, object_ = subject.strip(), predicate.strip(), object_.strip()
        if not subject or not predicate or not object_:
            raise ValueError("Graph relation values cannot be empty.")
        with self._connect() as con:
            sid = self._entity_id(con, subject)
            oid = self._entity_id(con, object_)
            con.execute(
                "INSERT OR IGNORE INTO kg_relations(subject_id, predicate, object_id) VALUES (?, ?, ?)",
                (sid, predicate, oid),
            )
        return GraphRelation(subject, predicate, object_)

    def learn_text(self, text: str) -> list[GraphRelation]:
        patterns = (
            (
                "uses",
                r"(?i)\b([A-Za-z][\w .-]{1,48})\s+(?:uses|uses the|depends on)\s+([A-Za-z][\w .:/-]{1,48})",
            ),
            (
                "is_a",
                r"(?i)\b([A-Za-z][\w .-]{1,48})\s+(?:is|are)\s+(?:a|an|the)\s+([A-Za-z][\w .-]{1,48})",
            ),
        )
        relations: list[GraphRelation] = []
        for predicate, pattern in patterns:
            for match in re.finditer(pattern, text):
                subject, object_ = (part.strip(" .,") for part in match.groups())
                relations.append(self.add_relation(subject, predicate, object_))
        return relations

    def search(self, name: str, limit: int = 20) -> list[GraphRelation]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT s.name AS subject, r.predicate AS predicate, o.name AS object
                FROM kg_relations r
                JOIN kg_entities s ON s.id = r.subject_id
                JOIN kg_entities o ON o.id = r.object_id
                WHERE lower(s.name) LIKE ? OR lower(o.name) LIKE ?
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (f"%{name.lower()}%", f"%{name.lower()}%", limit),
            ).fetchall()
        return [GraphRelation(row["subject"], row["predicate"], row["object"]) for row in rows]
