from __future__ import annotations

from jenefar.core.agent import AgentContext, AgentResult
from jenefar.core.router import AgentRouter


class MasterAgent:
    """Deterministic orchestration shell; model-backed planning is added next."""

    name = "master"

    def __init__(self, router: AgentRouter) -> None:
        self.router = router

    def dispatch(self, task: str) -> AgentResult:
        agent = self.router.route(task)
        return agent.run(AgentContext(task=task, metadata={"routed_by": self.name}))
