from __future__ import annotations

from jenefar.core.agent import AgentResult
from jenefar.core.router import AgentRouter


class MasterAgent:
    """Thin orchestration facade over the shared AgentRouter."""

    name = "master"

    def __init__(self, router: AgentRouter) -> None:
        self.router = router

    def dispatch(self, task: str) -> AgentResult:
        return self.router.dispatch(task, metadata={"routed_by": self.name})
