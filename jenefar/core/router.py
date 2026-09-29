from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Agent(Protocol):
    name: str
    description: str

    def can_handle(self, text: str) -> bool:
        ...

    def run(self, text: str) -> str:
        ...


@dataclass
class AgentRouter:
    agents: list[Agent]

    def route(self, text: str) -> Agent:
        for agent in self.agents:
            if agent.can_handle(text):
                return agent
        return next(
            (agent for agent in self.agents if agent.name == "research"),
            self.agents[-1],
        )
