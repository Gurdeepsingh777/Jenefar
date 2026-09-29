from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

@dataclass
class LLMResponse:
    text: str
    provider: str = "local"
    response_id: str | None = None

class LLMClient:
    """OpenAI Responses API boundary with optional web search and local tools."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        self._client = None

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def _client_or_raise(self):
        if not self.available():
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        instructions: str = "You are Jenefar, a precise and helpful multi-agent assistant.",
        use_web_search: bool = False,
        tool_broker=None,
        allow_action_tools: bool = False,
        max_tool_rounds: int = 4,
    ) -> LLMResponse:
        if not self.available():
            return LLMResponse(
                "LLM provider is not configured. Set OPENAI_API_KEY in .env.",
                "unconfigured",
            )

        client = self._client_or_raise()
        tools: list[dict[str, Any]] = []
        if use_web_search:
            tools.append({"type": "web_search"})
        if tool_broker is not None:
            tools.extend(tool_broker.schemas(allow_action_tools=allow_action_tools))

        request_input: Any = prompt
        last_response = None

        try:
            for _ in range(max_tool_rounds):
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "instructions": instructions,
                    "input": request_input,
                    "store": False,
                }
                if tools:
                    kwargs["tools"] = tools

                response = client.responses.create(**kwargs)
                last_response = response

                calls = [
                    item for item in (getattr(response, "output", []) or [])
                    if getattr(item, "type", None) == "function_call"
                ]

                if not calls:
                    return LLMResponse(
                        text=response.output_text or "The model returned no text.",
                        provider="openai",
                        response_id=getattr(response, "id", None),
                    )

                if tool_broker is None:
                    return LLMResponse(
                        "The model requested a tool, but no tool broker is configured.",
                        "tool_error",
                        getattr(response, "id", None),
                    )

                next_input = list(getattr(response, "output", []) or [])
                approval_required = False

                for call in calls:
                    try:
                        arguments = json.loads(getattr(call, "arguments", "{}") or "{}")
                    except json.JSONDecodeError:
                        arguments = {}

                    output = tool_broker.invoke(
                        getattr(call, "name", ""),
                        arguments,
                    )
                    try:
                        parsed = json.loads(output)
                    except json.JSONDecodeError:
                        parsed = {}

                    if parsed.get("status") == "approval_required":
                        approval_required = True

                    next_input.append({
                        "type": "function_call_output",
                        "call_id": getattr(call, "call_id", ""),
                        "output": output,
                    })

                if approval_required:
                    pending_ids = []
                    try:
                        pending_ids = [
                            json.loads(
                                tool_broker.invoke(
                                    getattr(c, "name", ""),
                                    json.loads(getattr(c, "arguments", "{}") or "{}"),
                                )
                            ).get("pending_id")
                            for c in calls
                        ]
                    except Exception:
                        pass
                    suffix = f" Pending approval id(s): {', '.join(x for x in pending_ids if x)}." if pending_ids else ""
                    return LLMResponse(
                        "A local tool requested explicit confirmation before execution." + suffix,
                        "approval_required",
                        getattr(response, "id", None),
                    )

                request_input = next_input

        except Exception as exc:
            return LLMResponse(
                f"LLM request failed: {type(exc).__name__}: {exc}",
                "error",
                getattr(last_response, "id", None) if last_response else None,
            )

        return LLMResponse(
            "The tool loop reached its safety limit without producing a final response.",
            "tool_limit",
            getattr(last_response, "id", None) if last_response else None,
        )
