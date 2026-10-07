from __future__ import annotations
import hashlib, sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class MemoryFact:
    id: int; key: str; value: str; confidence: float; source: str
    created_at: str; updated_at: str; active: bool

class MemoryLifecycle:
    """Confidence-aware facts with provenance and contradiction history."""
    def __init__(self, path: str | Path = "data/jenefar_memory.db") -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as con:
            con.executescript("""CREATE TABLE IF NOT EXISTS memory_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fact_key TEXT NOT NULL, value TEXT NOT NULL,
            value_hash TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.5, source TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(fact_key,value_hash));
            CREATE INDEX IF NOT EXISTS idx_memory_facts_key ON memory_facts(fact_key,active);""")
    @staticmethod
    def _now() -> str: return datetime.now(timezone.utc).isoformat()
    def remember(self, key: str, value: str, *, confidence: float = .8, source: str = "user") -> MemoryFact:
        key, value = " ".join(str(key).lower().split()).strip(), " ".join(str(value).split()).strip()
        if not key or not value: raise ValueError("key and value are required")
        confidence = max(0., min(1., float(confidence))); now = self._now()
        digest = hashlib.sha256(value.casefold().encode()).hexdigest()
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE memory_facts SET active=0,updated_at=? WHERE fact_key=? AND active=1 AND value_hash<>?",
                        (now,key,digest))
            con.execute("""INSERT INTO memory_facts(fact_key,value,value_hash,confidence,source,created_at,updated_at,active)
            VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(fact_key,value_hash) DO UPDATE SET confidence=excluded.confidence,
            source=excluded.source,updated_at=excluded.updated_at,active=1""",
                        (key,value,digest,confidence,source,now,now))
            row=con.execute("SELECT * FROM memory_facts WHERE fact_key=? AND value_hash=?",(key,digest)).fetchone()
        return MemoryFact(int(row[0]),row[1],row[2],float(row[4]),row[5],row[6],row[7],bool(row[8]))
    def recall(self, key: str, *, include_inactive: bool = False) -> list[MemoryFact]:
        sql="SELECT * FROM memory_facts WHERE fact_key=?"; params=(str(key).strip().lower(),)
        if not include_inactive: sql+=" AND active=1"
        sql+=" ORDER BY confidence DESC,updated_at DESC"
        with sqlite3.connect(self.path) as con: rows=con.execute(sql,params).fetchall()
        return [MemoryFact(int(r[0]),r[1],r[2],float(r[4]),r[5],r[6],r[7],bool(r[8])) for r in rows]
    def contradictions(self, key: str) -> list[MemoryFact]: return self.recall(key, include_inactive=True)
