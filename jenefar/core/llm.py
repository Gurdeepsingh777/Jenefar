from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from jenefar.offline.connectivity import internet_available
from jenefar.offline.local_llm import LocalLLMClient


@dataclass
class LLMResponse:
    text: str
    provider: str = "local"
    response_id: str | None = None
    pending_tools: list[dict[str, str]] = field(default_factory=list)


class LLMClient:
    """Online-first LLM boundary with automatic local-model fallback."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        self._client = None
        self.local = LocalLLMClient()

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def _client_or_raise(self):
        if not self.available():
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    @staticmethod
    def _tool_names(tools: list[dict[str, Any]]) -> list[str]:
        return [str(item.get("name", "")) for item in tools]

    def _complete_online(
        self,
        prompt: str,
        *,
        instructions: str,
        use_web_search: bool,
        tool_broker=None,
        allow_action_tools: bool,
        max_tool_rounds: int,
    ) -> LLMResponse:
        client = self._client_or_raise()
        tools: list[dict[str, Any]] = []
        if use_web_search:
            tools.append({"type": "web_search"})
        if tool_broker is not None:
            tools.extend(tool_broker.schemas(allow_action_tools=allow_action_tools))

        request_input: Any = prompt
        last_response = None

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
            pending_tools: list[dict[str, str]] = []

            for call in calls:
                try:
                    arguments = json.loads(getattr(call, "arguments", "{}") or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                output = tool_broker.invoke(getattr(call, "name", ""), arguments)
                try:
                    parsed = json.loads(output)
                except json.JSONDecodeError:
                    parsed = {}

                if parsed.get("status") == "approval_required":
                    approval_required = True
                    pending_id = str(parsed.get("pending_id") or "")
                    if pending_id:
                        pending_tools.append({
                            "pending_id": pending_id,
                            "tool": str(getattr(call, "name", "")),
                            "call_id": str(getattr(call, "call_id", "")),
                        })

                next_input.append({
                    "type": "function_call_output",
                    "call_id": getattr(call, "call_id", ""),
                    "output": output,
                })

            if approval_required:
                ids = ", ".join(item["pending_id"] for item in pending_tools)
                suffix = f" Pending approval id(s): {ids}." if ids else ""
                return LLMResponse(
                    "A local tool requested explicit confirmation before execution." + suffix,
                    "approval_required",
                    getattr(response, "id", None),
                    pending_tools=pending_tools,
                )

            request_input = next_input

        return LLMResponse(
            "The tool loop reached its safety limit without producing a final response.",
            "tool_limit",
            getattr(last_response, "id", None) if last_response else None,
        )

    def _complete_local(
        self,
        prompt: str,
        *,
        instructions: str,
        tool_broker=None,
        allow_action_tools: bool,
        max_tool_rounds: int,
    ) -> LLMResponse:
        tools = (
            tool_broker.schemas(
                allow_action_tools=allow_action_tools,
                include_confirmation_tools=True,
            )
            if tool_broker is not None
            else []
        )
        text, pending = self.local.complete(
            prompt=prompt,
            instructions=instructions,
            tools=tools,
            tool_broker=tool_broker,
            max_tool_rounds=max_tool_rounds,
        )
        if pending:
            return LLMResponse(
                text,
                "local_approval_required",
                pending_tools=pending,
            )
        return LLMResponse(text, "local")

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
        online = internet_available()
        api_key = self.available()

        if api_key and online:
            try:
                return self._complete_online(
                    prompt,
                    instructions=instructions,
                    use_web_search=use_web_search,
                    tool_broker=tool_broker,
                    allow_action_tools=allow_action_tools,
                    max_tool_rounds=max_tool_rounds,
                )
            except Exception as exc:
                online_error = f"{type(exc).__name__}: {exc}"
            else:
                online_error = ""
        else:
            online_error = (
                "internet unavailable"
                if not online
                else "OPENAI_API_KEY not configured"
            )

        try:
            fallback = self._complete_local(
                prompt,
                instructions=(
                    instructions
                    + "\\nYou are operating in local/offline mode. "
                    "Do not claim internet access or successful remote actions. "
                    "When an online-only task is requested, clearly list the blocked "
                    "online capability and continue with any local part that is possible."
                ),
                tool_broker=tool_broker,
                allow_action_tools=allow_action_tools,
                max_tool_rounds=max_tool_rounds,
            )
            if fallback.provider == "local":
                fallback.text = (
                    f"{fallback.text}"
                    if not online_error
                    else f"{fallback.text}"
                )
            return fallback
        except Exception as exc:
            if online_error:
                message = (
                    f"Online model unavailable ({online_error}); "
                    f"local model unavailable ({type(exc).__name__}: {exc})."
                )
            else:
                message = f"Local model unavailable ({type(exc).__name__}: {exc})."
            return LLMResponse(message, "offline_unavailable")
