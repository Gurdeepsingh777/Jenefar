from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from jenefar.core.agent import AgentContext, AgentResult, BaseAgent


@dataclass
class AgentRouter:
    agents: list[BaseAgent]

    def route(self, text: str) -> BaseAgent:
        for agent in self.agents:
            if agent.can_handle(text):
                return agent
        return next(
            (agent for agent in self.agents if agent.name == "research"),
            self.agents[-1],
        )

    def dispatch(self, text: str, *, metadata: dict | None = None) -> AgentResult:
        agent = self.route(text)
        return agent.run(AgentContext(task=text, metadata=metadata or {}))
