from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
@dataclass(frozen=True)
class Citation:
    source:str; title:str; locator:str; claim:str=""
    def as_dict(self): return {"source":self.source,"title":self.title,"locator":self.locator,"claim":self.claim}
def attach_citations(claims:Iterable[str],sources:Iterable[Citation]):
    src=list(sources); return [{"claim":str(c).strip(),"citations":[s.as_dict() for s in src[:3]]} for c in claims]
