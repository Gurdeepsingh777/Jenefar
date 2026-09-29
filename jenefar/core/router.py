from __future__ import annotations

from dataclasses import dataclass

from jenefar.core.agent import AgentContext, AgentResult, BaseAgent


@dataclass
class AgentRouter:
    agents: list[BaseAgent]

    def agent_by_name(self, name: str) -> BaseAgent | None:
        return next((agent for agent in self.agents if agent.name == name), None)

    def route(self, text: str, preferred_agent: str | None = None) -> BaseAgent:
        if preferred_agent:
            planned = self.agent_by_name(preferred_agent)
            if planned is not None:
                return planned

        for agent in self.agents:
            if agent.can_handle(text):
                return agent

        return self.agent_by_name("research") or self.agents[-1]

    def dispatch(
        self,
        text: str,
        *,
        metadata: dict | None = None,
    ) -> AgentResult:
        metadata = metadata or {}
        agent = self.route(
            text,
            preferred_agent=metadata.get("planned_agent"),
        )
        result = agent.run(AgentContext(task=text, metadata=metadata))
        result.metadata.setdefault("routing", {})
        result.metadata["routing"].update({
            "agent": agent.name,
            "planned_agent": metadata.get("planned_agent"),
            "planner_confidence": metadata.get("planner_confidence"),
            "planner_reason": metadata.get("planner_reason"),
        })
        return result
