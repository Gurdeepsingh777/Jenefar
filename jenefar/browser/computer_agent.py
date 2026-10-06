from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Any
import time

class ComputerAdapter(Protocol):
    def observe(self) -> Any: ...
    def act(self, action: dict[str,Any]) -> Any: ...
    def verify(self, before: Any, after: Any, action: dict[str,Any]) -> bool: ...

@dataclass
class ComputerStep:
    action: dict[str,Any]
    observation: Any
    verified: bool
    error: str|None=None

class ComputerAgent:
    def __init__(self, adapter: ComputerAdapter, max_steps: int=8):
        self.adapter=adapter; self.max_steps=max(1,min(max_steps,50))
    def execute(self, planner, goal: str) -> list[ComputerStep]:
        steps=[]; observation=self.adapter.observe()
        for _ in range(self.max_steps):
            action=planner(goal, observation, steps)
            if not action: break
            started=time.monotonic()
            try:
                result=self.adapter.act(action)
                verified=self.adapter.verify(observation,result,action)
                steps.append(ComputerStep(action,result,verified))
                observation=result
                if verified and action.get("terminal"): break
            except Exception as exc:
                steps.append(ComputerStep(action,observation,False,f"{type(exc).__name__}: {exc}"))
                break
        return steps
