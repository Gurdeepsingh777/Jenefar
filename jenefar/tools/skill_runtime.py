from __future__ import annotations
from dataclasses import dataclass, field
import time

@dataclass(frozen=True)
class SkillManifest:
    name: str
    version: str
    description: str = ""
    permissions: frozenset[str] = frozenset()
    dependencies: tuple[str,...] = ()

@dataclass
class SkillHealth:
    calls: int=0
    failures: int=0
    last_error: str|None=None
    last_latency_ms: float|None=None
    available: bool=True

class SkillRuntime:
    def __init__(self):
        self.manifests: dict[str,SkillManifest]={}
        self.health: dict[str,SkillHealth]={}
    def register(self, manifest: SkillManifest) -> None:
        if manifest.name in self.manifests: raise ValueError(f"skill already registered: {manifest.name}")
        self.manifests[manifest.name]=manifest; self.health[manifest.name]=SkillHealth()
    def available(self, name: str, permissions=()) -> bool:
        m=self.manifests.get(name)
        return bool(m and m.permissions.issubset(set(permissions)) and all(dep in self.manifests for dep in m.dependencies) and self.health[name].available)
    def record(self, name: str, *, ok: bool, latency_ms: float, error: str|None=None) -> None:
        h=self.health[name]; h.calls+=1; h.last_latency_ms=latency_ms
        if not ok: h.failures+=1; h.last_error=error
    def disable(self, name: str, reason: str="") -> None:
        self.health[name].available=False; self.health[name].last_error=reason
    def snapshot(self) -> dict:
        return {name: {"version":m.version, "permissions":sorted(m.permissions), "dependencies":list(m.dependencies), "health":vars(self.health[name])} for name,m in self.manifests.items()}
