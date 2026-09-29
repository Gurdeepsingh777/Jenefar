from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentContext:
    task: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    content: str
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    name = "base"
    description = "Base Jenefar specialist"

    def can_handle(self, text: str) -> bool:
        return False

    def run(self, context: AgentContext) -> AgentResult:
        raise NotImplementedError


class FunctionAgent(BaseAgent):
    def __init__(self, name: str, description: str, handler: Callable[[AgentContext], str], matcher: Callable[[str], bool]):
        self.name = name
        self.description = description
        self._handler = handler
        self._matcher = matcher

    def can_handle(self, text: str) -> bool:
        return self._matcher(text)

    def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(agent=self.name, content=self._handler(context))
