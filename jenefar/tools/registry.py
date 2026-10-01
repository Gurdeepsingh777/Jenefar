from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[[dict[str, Any]], Any]
    parameters: dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    })
    requires_confirmation: bool = False
    action: bool = False
    critical: bool = False

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def openai_tools(self, *, include_confirmation_tools: bool = False, include_action_tools: bool = False) -> list[dict[str, Any]]:
        tools = []
        for spec in self._tools.values():
            if spec.critical and not include_confirmation_tools:
                continue
            if spec.action and not include_action_tools:
                continue
            tools.append({
                "type": "function",
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                "strict": False,
            })
        return tools
