from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)
ToolHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    """Register async/sync Python tools and expose OpenAI-compatible JSON schemas."""

    def __init__(self, *, max_output_chars: int = 12000) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.max_output_chars = max(1000, int(max_output_chars))

    def tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> Callable[[ToolHandler], ToolHandler]:
        if not name or not name.replace("_", "").isalnum() or len(name) > 64:
            raise ValueError("Tool names must be 1-64 characters containing letters, numbers or underscores.")
        if not description.strip():
            raise ValueError("Tool descriptions must not be empty.")
        if parameters.get("type") != "object":
            raise ValueError("Tool parameters must use a JSON Schema object.")
        if parameters.get("additionalProperties") is not False:
            raise ValueError("Tool schemas must set additionalProperties=false.")

        def decorator(handler: ToolHandler) -> ToolHandler:
            if name in self._tools:
                raise ValueError(f"Tool is already registered: {name}")
            self._tools[name] = ToolDefinition(
                name=name,
                description=description.strip(),
                parameters=parameters,
                handler=handler,
            )
            return handler

        return decorator

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        definition = self._tools.get(name)
        if definition is None:
            return self._encode({"ok": False, "error": f"Unknown tool: {name}"})
        if not isinstance(arguments, dict):
            return self._encode({"ok": False, "error": "Tool arguments must be a JSON object."})

        try:
            result = definition.handler(arguments)
            if inspect.isawaitable(result):
                result = await result
            return self._encode({"ok": True, "result": result})
        except Exception as exc:  # Tool errors are observations, not agent crashes.
            logger.warning("Tool %s failed: %s: %s", name, type(exc).__name__, exc)
            message = str(exc).strip() or type(exc).__name__
            return self._encode({
                "ok": False,
                "tool": name,
                "error": message[:2000],
                "error_type": type(exc).__name__,
            })

    def _encode(self, payload: dict[str, Any]) -> str:
        try:
            encoded = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            encoded = json.dumps({"ok": False, "error": "Tool returned a non-serializable result."})
        if len(encoded) <= self.max_output_chars:
            return encoded
        preview_size = max(200, self.max_output_chars - 500)
        return json.dumps({
            "ok": payload.get("ok", False),
            "truncated": True,
            "result_preview": encoded[:preview_size],
            "message": "Tool output exceeded the configured limit; preview only.",
        }, ensure_ascii=False)
