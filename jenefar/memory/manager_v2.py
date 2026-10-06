from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, math, time

@dataclass
class MemoryRecord:
    memory_id: str
    content: str
    kind: str = "semantic"
    importance: float = 0.5
    created_at: float = 0.0
    updated_at: float = 0.0
    provenance: str = "runtime"
    tags: tuple[str,...] = ()
    supersedes: str | None = None

class MemoryManagerV2:
    def __init__(self, half_life_days: float = 30.0):
        self.records: dict[str, MemoryRecord] = {}
        self.half_life = max(1.0, half_life_days)
    def upsert(self, content: str, *, kind="semantic", importance=0.5, provenance="runtime", tags=(), memory_id=None) -> MemoryRecord:
        now=time.time(); norm=" ".join(content.split()).lower()
        key=memory_id or hashlib.sha256(norm.encode()).hexdigest()[:20]
        rec=self.records.get(key)
        if rec:
            rec.content=content; rec.updated_at=now; rec.importance=max(rec.importance,float(importance)); return rec
        rec=MemoryRecord(key, content, kind, max(0,min(1,float(importance))), now, now, provenance, tuple(tags))
        self.records[key]=rec; return rec
    def forget(self, memory_id: str) -> bool:
        return self.records.pop(memory_id, None) is not None
    def _score(self, rec: MemoryRecord, query: str, now: float) -> float:
        tokens=set(query.lower().split()); words=set(rec.content.lower().split())
        lexical=len(tokens & words)/max(1,len(tokens))
        age=max(0, now-rec.updated_at)/86400
        decay=0.5 ** (age/self.half_life)
        return 0.65*lexical + 0.25*rec.importance + 0.10*decay
    def search(self, query: str, limit: int=8) -> list[MemoryRecord]:
        now=time.time()
        return sorted(self.records.values(), key=lambda r:self._score(r,query,now), reverse=True)[:max(1,limit)]
    def snapshot(self) -> dict:
        return {"count":len(self.records), "kinds": {k:sum(r.kind==k for r in self.records.values()) for k in {r.kind for r in self.records.values()}}}
