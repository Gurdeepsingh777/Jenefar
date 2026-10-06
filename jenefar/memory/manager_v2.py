from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib, json, os, threading, time
from pathlib import Path

@dataclass
class MemoryRecord:
    memory_id: str
    content: str
    kind: str = "semantic"
    importance: float = 0.5
    created_at: float = 0.0
    updated_at: float = 0.0
    provenance: str = "runtime"
    tags: tuple[str, ...] = ()
    supersedes: str | None = None

class MemoryManagerV2:
    def __init__(self, half_life_days: float = 30.0, path: str | Path | None = None):
        self.records: dict[str, MemoryRecord] = {}
        self.half_life = max(1.0, float(half_life_days))
        self.path = Path(path or os.getenv("JENEFAR_MEMORY_V2_PATH", "data/memory_v2.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        with self._lock:
            for line in lines:
                try:
                    raw = json.loads(line)
                    record = MemoryRecord(**raw, tags=tuple(raw.get("tags", ())))
                    self.records[record.memory_id] = record
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue

    def _persist_locked(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text("".join(json.dumps(asdict(r), ensure_ascii=False, separators=(",", ":")) + "\n" for r in self.records.values()), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass

    def upsert(self, content: str, *, kind="semantic", importance=0.5, provenance="runtime", tags=(), memory_id=None) -> MemoryRecord:
        now = time.time()
        norm = " ".join(str(content).split()).lower()
        if not norm:
            raise ValueError("memory content cannot be empty")
        key = memory_id or hashlib.sha256(norm.encode()).hexdigest()[:20]
        with self._lock:
            rec = self.records.get(key)
            if rec:
                rec.content = str(content)
                rec.updated_at = now
                rec.importance = max(rec.importance, max(0.0, min(1.0, float(importance))))
                rec.tags = tuple(tags) or rec.tags
            else:
                rec = MemoryRecord(key, str(content), str(kind), max(0.0, min(1.0, float(importance))), now, now, str(provenance), tuple(tags))
                self.records[key] = rec
            self._persist_locked()
            return rec

    def forget(self, memory_id: str) -> bool:
        with self._lock:
            removed = self.records.pop(memory_id, None) is not None
            if removed: self._persist_locked()
            return removed

    def _score(self, rec: MemoryRecord, query: str, now: float) -> float:
        tokens = set(query.lower().split())
        words = set(rec.content.lower().split())
        lexical = len(tokens & words) / max(1, len(tokens))
        age = max(0, now - rec.updated_at) / 86400
        decay = 0.5 ** (age / self.half_life)
        return 0.65 * lexical + 0.25 * rec.importance + 0.10 * decay

    def search(self, query: str, limit: int = 8) -> list[MemoryRecord]:
        with self._lock:
            now = time.time()
            return sorted(self.records.values(), key=lambda r: self._score(r, query, now), reverse=True)[:max(1, min(int(limit), 100))]

    def snapshot(self) -> dict:
        with self._lock:
            return {"count": len(self.records), "persistent": True, "path": str(self.path), "kinds": {k: sum(r.kind == k for r in self.records.values()) for k in {r.kind for r in self.records.values()}}}
