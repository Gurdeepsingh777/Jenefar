from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from jenefar.core.model_router import ModelRouter
from jenefar.core.provider_pool import ProviderPool, is_retryable_provider_error
from jenefar.offline.connectivity import internet_available
from jenefar.offline.local_llm import LocalLLMClient


@dataclass
class LLMResponse:
    text: str
    provider: str = "local"
    response_id: str | None = None
    pending_tools: list[dict[str, str]] = field(default_factory=list)
    model: str | None = None
    model_role: str | None = None


class LLMClient:
    """Multi-provider online LLM boundary with automatic failover and local fallback."""

    def __init__(self, model: str | None = None, model_role: str | None = None):
        self.explicit_model = model
        self.default_role = model_role or "fast"
        selected = ModelRouter().resolve(self.default_role, explicit_model=model)
        self.model = selected.model
        self.model_role = selected.role
        self._clients: dict[str, Any] = {}
        self.providers = ProviderPool()
        self.local = LocalLLMClient(model_role=self.default_role)

    def available(self) -> bool:
        return any(self.providers.configured(name) for name in self.providers.order())

    def selected_model(self, model_role: str | None = None) -> tuple[str, str]:
        role = (model_role or self.default_role or "fast").strip().lower()
        selected = ModelRouter().resolve(role, explicit_model=self.explicit_model)
        return selected.model, selected.role

    def provider_status(self, model_role: str | None = None) -> dict[str, dict]:
        role = model_role or self.default_role
        return self.providers.status(role)

    def _client(self, provider: str):
        if provider in self._clients:
            return self._clients[provider]

        config = self.providers.CONFIGS[provider]
        from openai import OpenAI

        timeout = min(max(float(os.getenv("JENEFAR_PROVIDER_TIMEOUT_SECONDS", "45")), 5.0), 300.0)
        kwargs = {"api_key": self.providers.api_key(provider), "timeout": timeout, "max_retries": 0}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._clients[provider] = OpenAI(**kwargs)
        return self._clients[provider]

    @staticmethod
    def _chat_tools(tool_broker, allow_action_tools: bool) -> list[dict[str, Any]]:
        """Convert Jenefar's Responses-style function schemas to Chat Completions format."""
        if tool_broker is None:
            return []
        tools = tool_broker.schemas(
            allow_action_tools=allow_action_tools,
            include_confirmation_tools=True,
        )
        converted = []
        for tool in tools:
            if tool.get("type") != "function":
                continue
            converted.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    }),
                },
            })
        return converted

    @staticmethod
    def _tool_result(call: Any, output: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": getattr(call, "id", ""),
            "content": output,
        }

    @staticmethod
    def _tool_signature(name: str, arguments: dict[str, Any]) -> str:
        try:
            encoded = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        except TypeError:
            encoded = str(arguments)
        return f"{name}:{encoded}"

    @staticmethod
    def _repeated_tool_response(
        provider: str,
        response_id: str | None,
        model: str,
        model_role: str,
    ) -> LLMResponse:
        return LLMResponse(
            "I stopped a repeated tool loop. The latest tool result is already visible in the workspace panel. "
            "A more specific next step is needed before I run that same action again.",
            provider,
            response_id,
            model=model,
            model_role=model_role,
        )

    @staticmethod
    def _remaining_timeout(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Jenefar execution budget exhausted")
        return max(0.5, remaining)

    def _complete_openai_responses(
        self,
        provider: str,
        prompt: str,
        *,
        instructions: str,
        use_web_search: bool,
        tool_broker=None,
        allow_action_tools: bool,
        max_tool_rounds: int,
        model: str,
        model_role: str,
        deadline: float | None = None,
    ) -> LLMResponse:
        client = self._client(provider)
        tools: list[dict[str, Any]] = []
        if use_web_search and provider == "openai":
            tools.append({"type": "web_search"})
        if tool_broker is not None:
            tools.extend(tool_broker.schemas(allow_action_tools=allow_action_tools))

        request_input: Any = prompt
        last_response = None
        tool_counts: Counter[str] = Counter()
        for _ in range(max(1, min(max_tool_rounds, 20))):
            kwargs: dict[str, Any] = {
                "model": model,
                "instructions": instructions,
                "input": request_input,
                "store": False,
            }
            if tools:
                kwargs["tools"] = tools
            timeout = self._remaining_timeout(deadline)
            if timeout is not None:
                kwargs["timeout"] = timeout
            response = client.responses.create(**kwargs)
            last_response = response
            calls = [
                item for item in (getattr(response, "output", []) or [])
                if getattr(item, "type", None) == "function_call"
            ]
            if not calls:
                return LLMResponse(
                    text=response.output_text or "The model returned no text.",
                    provider=provider,
                    response_id=getattr(response, "id", None),
                    model=model,
                    model_role=model_role,
                )
            if tool_broker is None:
                return LLMResponse(
                    "The model requested a tool, but no tool broker is configured.",
                    "tool_error",
                    getattr(response, "id", None),
                    model=model,
                    model_role=model_role,
                )

            next_input = list(getattr(response, "output", []) or [])
            pending_tools: list[dict[str, str]] = []
            for call in calls:
                try:
                    arguments = json.loads(getattr(call, "arguments", "{}") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool_name = getattr(call, "name", "")
                signature = self._tool_signature(tool_name, arguments)
                tool_counts[signature] += 1
                if tool_counts[signature] > 1:
                    return self._repeated_tool_response(
                        provider,
                        getattr(response, "id", None),
                        model,
                        model_role,
                    )
                self._remaining_timeout(deadline)
                output = tool_broker.invoke(tool_name, arguments)
                try:
                    parsed = json.loads(output)
                except json.JSONDecodeError:
                    parsed = {}
                if parsed.get("status") == "approval_required":
                    pending_id = str(parsed.get("pending_id") or "")
                    if pending_id:
                        pending_tools.append({
                            "pending_id": pending_id,
                            "tool": str(getattr(call, "name", "")),
                            "call_id": str(getattr(call, "call_id", "")),
                            "prompt": str(parsed.get("user_prompt") or ""),
                        })
                next_input.append({
                    "type": "function_call_output",
                    "call_id": getattr(call, "call_id", ""),
                    "output": output,
                })

            if pending_tools:
                prompts = [item.get("prompt", "").strip() for item in pending_tools if item.get("prompt")]
                text = " ".join(prompts) if prompts else "Is action ke liye aapki confirmation chahiye."
                return LLMResponse(
                    text,

                    "approval_required",
                    getattr(response, "id", None),
                    pending_tools=pending_tools,
                    model=model,
                    model_role=model_role,
                )
            request_input = next_input

        return LLMResponse(
            "The tool loop reached its safety limit without producing a final response.",
            "tool_limit",
            getattr(last_response, "id", None) if last_response else None,
            model=model,
            model_role=model_role,
        )

    def _complete_chat(
        self,
        provider: str,
        prompt: str,
        *,
        instructions: str,
        tool_broker=None,
        allow_action_tools: bool,
        max_tool_rounds: int,
        model: str,
        model_role: str,
        deadline: float | None = None,
    ) -> LLMResponse:
        client = self._client(provider)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ]
        tools = self._chat_tools(tool_broker, allow_action_tools)
        tool_counts: Counter[str] = Counter()

        for _ in range(max(1, min(max_tool_rounds, 20))):
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            timeout = self._remaining_timeout(deadline)
            if timeout is not None:
                kwargs["timeout"] = timeout
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message
            tool_calls = getattr(message, "tool_calls", None) or []

            if not tool_calls:
                return LLMResponse(
                    text=getattr(message, "content", None) or "The model returned no text.",
                    provider=provider,
                    response_id=getattr(response, "id", None),
                    model=model,
                    model_role=model_role,
                )

            if tool_broker is None:
                return LLMResponse(
                    "The model requested a tool, but no tool broker is configured.",
                    "tool_error",
                    getattr(response, "id", None),
                    model=model,
                    model_role=model_role,
                )

            assistant_message = {
                "role": "assistant",
                "content": getattr(message, "content", None),
                "tool_calls": [
                    {
                        "id": getattr(call, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(getattr(call, "function", None), "name", ""),
                            "arguments": getattr(getattr(call, "function", None), "arguments", "{}"),
                        },
                    }
                    for call in tool_calls
                ],
            }
            messages.append(assistant_message)
            pending_tools: list[dict[str, str]] = []

            for call in tool_calls:
                function = getattr(call, "function", None)
                name = str(getattr(function, "name", ""))
                try:
                    arguments = json.loads(getattr(function, "arguments", "{}") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                signature = self._tool_signature(name, arguments)
                tool_counts[signature] += 1
                if tool_counts[signature] > 1:
                    return self._repeated_tool_response(
                        provider,
                        getattr(response, "id", None),
                        model,
                        model_role,
                    )
                self._remaining_timeout(deadline)
                output = tool_broker.invoke(name, arguments)
                try:
                    parsed = json.loads(output)
                except json.JSONDecodeError:
                    parsed = {}
                if parsed.get("status") == "approval_required":
                    pending_id = str(parsed.get("pending_id") or "")
                    if pending_id:
                        pending_tools.append({
                            "pending_id": pending_id,
                            "tool": name,
                            "call_id": str(getattr(call, "id", "")),
                            "prompt": str(parsed.get("user_prompt") or ""),
                        })
                messages.append(self._tool_result(call, output))

            if pending_tools:
                prompts = [item.get("prompt", "").strip() for item in pending_tools if item.get("prompt")]
                text = " ".join(prompts) if prompts else "Is action ke liye aapki confirmation chahiye."
                return LLMResponse(
                    text,

                    "approval_required",
                    getattr(response, "id", None),
                    pending_tools=pending_tools,
                    model=model,
                    model_role=model_role,
                )

        return LLMResponse(
            "The tool loop reached its safety limit without producing a final response.",
            "tool_limit",
            model=model,
            model_role=model_role,
        )

    def _complete_online(
        self,
        provider: str,
        prompt: str,
        *,
        instructions: str,
        use_web_search: bool,
        tool_broker=None,
        allow_action_tools: bool,
        max_tool_rounds: int,
        model: str,
        model_role: str,
        deadline: float | None = None,
    ) -> LLMResponse:
        if provider == "openai":
            return self._complete_openai_responses(
                provider, prompt, instructions=instructions,
                use_web_search=use_web_search, tool_broker=tool_broker,
                allow_action_tools=allow_action_tools,
                max_tool_rounds=max_tool_rounds, model=model,
                model_role=model_role,
                deadline=deadline,
            )
        return self._complete_chat(
            provider, prompt, instructions=instructions,
            tool_broker=tool_broker, allow_action_tools=allow_action_tools,
            max_tool_rounds=max_tool_rounds, model=model, model_role=model_role,
            deadline=deadline,
        )

    def _complete_local(
        self,
        prompt: str,
        *,
        instructions: str,
        tool_broker=None,
        allow_action_tools: bool,
        max_tool_rounds: int,
        model_role: str,
        deadline: float | None = None,
    ) -> LLMResponse:
        tools = (
            tool_broker.schemas(
                allow_action_tools=allow_action_tools,
                include_confirmation_tools=True,
            )
            if tool_broker is not None else []
        )
        text, pending = self.local.complete(
            prompt=prompt, instructions=instructions, tools=tools,
            tool_broker=tool_broker, max_tool_rounds=max_tool_rounds,
            model_role=model_role,
        )
        if pending:
            return LLMResponse(
                text, "local_approval_required", pending_tools=pending,
                model=self.local.model, model_role=model_role,
            )
        return LLMResponse(
            text, "local", model=self.local.model, model_role=model_role,
        )

    def complete(
        self,
        prompt: str,
        *,
        instructions: str = "You are Jenefar, a precise and helpful multi-agent assistant.",
        use_web_search: bool = False,
        tool_broker=None,
        allow_action_tools: bool = False,
        max_tool_rounds: int = 4,
        model_role: str | None = None,
        deadline: float | None = None,
    ) -> LLMResponse:
        online = internet_available()
        _, selected_role = self.selected_model(model_role)
        if deadline is not None and deadline <= time.monotonic():
            raise TimeoutError("Jenefar execution budget exhausted")
        failures: list[str] = []

        if online:
            for provider in self.providers.order_for_role(selected_role):
                started = time.perf_counter()
                if not self.providers.available(provider):
                    continue
                model = self.explicit_model or self.providers.model(provider, selected_role)
                try:
                    result = self._complete_online(
                        provider, prompt, instructions=instructions,
                        use_web_search=use_web_search, tool_broker=tool_broker,
                        allow_action_tools=allow_action_tools,
                        max_tool_rounds=max_tool_rounds, model=model,
                        model_role=selected_role, deadline=deadline,
                    )
                    self.providers.record_latency(provider, time.perf_counter() - started, success=True)
                    self.providers.reset(provider)
                    return result
                except Exception as exc:
                    self.providers.record_latency(provider, time.perf_counter() - started, success=False)
                    error = f"{type(exc).__name__}: {exc}"
                    failures.append(f"{provider}: {error}")
                    if is_retryable_provider_error(exc):
                        self.providers.cooldown(provider)
                        continue
                    # A non-retryable provider error should still allow another
                    # configured provider to answer, but it is not cooled down.
                    continue

        online_error = "; ".join(failures) if failures else (
            "internet unavailable" if not online else "no configured online provider"
        )

        if os.getenv("JENEFAR_DISABLE_LOCAL_FALLBACK", "").strip().lower() in {
            "1", "true", "yes", "on"
        }:
            return LLMResponse(
                f"All online providers unavailable ({online_error}). "
                "Local fallback is disabled for this run.",
                "online_unavailable",
                model_role=selected_role,
            )

        try:
            return self._complete_local(
                prompt,
                instructions=(
                    instructions
                    + "\nYou are operating in local/offline mode. "
                    "Do not claim internet access or successful remote actions. "
                    "When an online-only task is requested, clearly list the blocked "
                    "online capability and continue with any local part that is possible."
                ),
                tool_broker=tool_broker,
                allow_action_tools=allow_action_tools,
                max_tool_rounds=max_tool_rounds,
                model_role=selected_role,
                deadline=deadline,
            )
        except Exception as exc:
            return LLMResponse(
                f"Online providers unavailable ({online_error}); "
                f"local model unavailable ({type(exc).__name__}: {exc}).",
                "offline_unavailable",
                model_role=selected_role,
            )
