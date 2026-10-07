from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
from jenefar.core.self_healing import SelfHealingRuntime

@dataclass
class TaskStepResult:
    step_id: str
    status: str
    result: Any = None
    error: str = ""

@dataclass
class AutonomousRun:
    task: str
    status: str
    steps: list[TaskStepResult] = field(default_factory=list)
    attempts: int = 0
    replans: int = 0
    def as_dict(self) -> dict[str, Any]:
        return {"task": self.task, "status": self.status, "attempts": self.attempts, "replans": self.replans,
                "steps": [{"step_id": s.step_id, "status": s.status, "result": s.result, "error": s.error} for s in self.steps]}

class AutonomousTaskEngine:
    """Bounded observe -> act -> verify -> recover loop."""
    def __init__(self, *, planner: Callable[[str], list[dict[str, Any]]], executor: Callable[[dict[str, Any]], Any],
                 verifier: Callable[[dict[str, Any], Any], bool],
                 replanner: Callable[[str, list[TaskStepResult]], list[dict[str, Any]]] | None = None,
                 recovery: SelfHealingRuntime | None = None, max_steps: int = 12) -> None:
        self.planner, self.executor, self.verifier = planner, executor, verifier
        self.replanner = replanner or (lambda task, _history: self.planner(task))
        self.recovery = recovery or SelfHealingRuntime()
        self.max_steps = max(1, min(int(max_steps), 50))

    def run(self, task: str) -> AutonomousRun:
        run = AutonomousRun(task=task, status="running")
        plan, cursor = list(self.planner(task))[:self.max_steps], 0
        while cursor < self.max_steps and plan:
            step = dict(plan[cursor]); step_id = str(step.get("id") or f"step-{cursor + 1}"); run.attempts += 1
            try:
                result = self.recovery.run(f"autonomous:{step_id}", lambda: self.executor(step),
                                           metadata={"approval_required": bool(step.get("approval_required"))})
                if not self.verifier(step, result):
                    run.steps.append(TaskStepResult(step_id, "verification_failed", result=result)); run.replans += 1
                    replacement = self.replanner(task, run.steps)
                    if replacement: plan, cursor = replacement[:self.max_steps], 0; continue
                    run.status = "failed"; return run
                run.steps.append(TaskStepResult(step_id, "completed", result=result)); cursor += 1
            except Exception as exc:
                run.steps.append(TaskStepResult(step_id, "error", error=f"{type(exc).__name__}: {exc}")); run.replans += 1
                replacement = self.replanner(task, run.steps)
                if replacement: plan, cursor = replacement[:self.max_steps], 0; continue
                run.status = "failed"; return run
        run.status = "completed" if plan else "no_plan"
        return run
