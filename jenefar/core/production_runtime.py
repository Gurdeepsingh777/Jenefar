from __future__ import annotations

import time
from typing import Any

from jenefar.evaluation.benchmark import BenchmarkRunner
from jenefar.execution.task_graph import TaskGraph
from jenefar.memory.manager_v2 import MemoryManagerV2
from jenefar.observability.runtime_metrics import RuntimeMetrics
from jenefar.production.readiness import check as readiness_check
from jenefar.security.policy import AuditChain, ApprovalManager
from jenefar.tools.skill_runtime import SkillRuntime
from jenefar.voice.session_v2 import VoiceSession


class ProductionRuntime:
    """Shared production controls used by the live orchestrator and dashboard.

    The class deliberately wraps the phase 13-24 primitives behind one small
    runtime surface so individual features can be exercised without bypassing
    the existing approval, lifecycle, tracing, or cancellation layers.
    """

    def __init__(self) -> None:
        self.metrics = RuntimeMetrics()
        self.memory = MemoryManagerV2()
        self.skills = SkillRuntime()
        self.voice = VoiceSession()
        self.benchmarks = BenchmarkRunner()
        self.approvals = ApprovalManager()
        self.audit = AuditChain()
        self._started: dict[str, float] = {}

    def task_started(self, task_id: str, task: str, *, agent: str = "") -> None:
        now = time.monotonic()
        self._started[task_id] = now
        self.metrics.inc("tasks_started")
        self.audit.append({
            "type": "task_started",
            "task_id": task_id,
            "agent": agent,
            "event": task[:512],
        })

    def task_finished(
        self,
        task_id: str,
        *,
        state: str,
        agent: str = "",
        provider: str = "",
        error: str = "",
    ) -> None:
        started = self._started.pop(task_id, None)
        if started is not None:
            self.metrics.observe("task_latency_seconds", max(0.0, time.monotonic() - started))
        self.metrics.inc(f"tasks_{state}")
        self.audit.append({
            "type": "task_finished",
            "task_id": task_id,
            "agent": agent,
            "provider": provider,
            "state": state,
            "event": error[:512],
        })

    def remember(self, content: str, *, kind: str = "semantic", importance: float = 0.5, provenance: str = "runtime", tags: tuple[str, ...] = ()):
        return self.memory.upsert(
            content,
            kind=kind,
            importance=importance,
            provenance=provenance,
            tags=tags,
        )

    def build_task_graph(self, checkpoint_path: str | None = None) -> TaskGraph:
        return TaskGraph(checkpoint_path)

    def readiness(self) -> dict[str, Any]:
        return readiness_check()

    def snapshot(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics.snapshot(),
            "memory": self.memory.snapshot(),
            "skills": self.skills.snapshot(),
            "voice": {
                "active": self.voice.active is not None,
                "history_count": len(self.voice.history),
            },
            "readiness": self.readiness(),
        }


__all__ = ["ProductionRuntime"]
