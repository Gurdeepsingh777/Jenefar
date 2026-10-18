from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class VisualElement:
    element_id: str
    role: str
    label: str
    x: float
    y: float
    width: float
    height: float
    confidence: float=1.0
    def center(self) -> tuple[float,float]: return (self.x+self.width/2, self.y+self.height/2)

class GroundingEngine:
    def rank(self, elements: list[VisualElement], query: str, role: str|None=None) -> list[tuple[VisualElement,float]]:
        q=set(query.lower().split()); scored=[]
        for e in elements:
            label=set(e.label.lower().split()); lexical=len(q&label)/max(1,len(q))
            role_bonus=0.2 if role and e.role.lower()==role.lower() else 0
            scored.append((e, 0.7*lexical+0.2*e.confidence+role_bonus))
        return sorted(scored,key=lambda x:x[1],reverse=True)
    def require_confident(self, ranked, threshold=0.65) -> VisualElement:
        if not ranked or ranked[0][1] < threshold: raise LookupError("no sufficiently confident visual target")
        return ranked[0][0]
