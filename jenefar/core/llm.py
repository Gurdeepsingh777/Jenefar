from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from jenefar.core.model_router import ModelRouter
from jenefar.core.provider_pool import (
    ProviderPool,
    is_quota_exhausted_provider_error,
    is_retryable_provider_error,
)
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
        if any(self.providers.configured(name) for name in self.providers.order()):
            return True
        # Local-only installations must still be able to run the orchestrator.
        # Detection is intentionally deferred until no cloud provider is configured.
        try:
            return self.local.detect(model_role=self.default_role) is not None
        except Exception:
            return False

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

        kwargs = {"api_key": self.providers.api_key(provider)}
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
            response = client.responses.create(**kwargs)
            last_response = response
            calls = [
                item for item in (getattr(response, "output", []) or [])
                if getattr(item, "type", None) == "function_call"
            ]
            if not calls:
                answer = str(getattr(response, "output_text", "") or "").strip()
                if not answer:
                    # An empty Responses API result is a provider failure, not a
                    # successful answer. Raising allows failover to another cloud
                    # provider and then the local Ollama model.
                    raise RuntimeError(f"{provider} returned an empty text response.")
                return LLMResponse(
                    text=answer,
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
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message
            tool_calls = getattr(message, "tool_calls", None) or []

            if not tool_calls:
                answer = str(getattr(message, "content", None) or "").strip()
                if not answer:
                    raise RuntimeError(f"{provider} returned an empty chat response.")
                return LLMResponse(
                    text=answer,
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
    ) -> LLMResponse:
        if provider == "openai":
            return self._complete_openai_responses(
                provider, prompt, instructions=instructions,
                use_web_search=use_web_search, tool_broker=tool_broker,
                allow_action_tools=allow_action_tools,
                max_tool_rounds=max_tool_rounds, model=model,
                model_role=model_role,
            )
        return self._complete_chat(
            provider, prompt, instructions=instructions,
            tool_broker=tool_broker, allow_action_tools=allow_action_tools,
            max_tool_rounds=max_tool_rounds, model=model, model_role=model_role,
        )

    @staticmethod
    def _select_local_tools(prompt: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep local-model context small by advertising tools only for action tasks."""
        if not tools:
            return []
        mode = os.getenv("JENEFAR_LOCAL_LLM_TOOL_MODE", "auto").strip().lower()
        if mode in {"all", "always"}:
            return tools
        if mode in {"none", "never", "off", "false", "0"}:
            return []

        task = str(prompt or "").casefold()
        categories = [
            (
                ("\\brea\\b", "\\bmcp\\b", "reverse engineer", "reverse-engineer"),
                ("rea_",),
            ),
            (
                ("repository", "\\brepo\\b", "project", "source code", "codebase", "file", "folder",
                 "\\bgit\\b", "commit", "pull request", "pytest", "test suite", "debug", "refactor",
                 "edit code", "modify code", "fix code", "fix this bug", "write code", "update code"),
                ("repository_", "workspace_", "file_", "python_", "local_development_", "git_", "terminal_execute"),
            ),
            (
                ("search the web", "web search", "search online", "latest news", "website", "url",
                 "fetch url", "github repository", "look this up online"),
                ("research_", "github_", "web_", "fetch_", "search_web", "url_"),
            ),
            (
                ("desktop", "screenshot", "screen", "window", "gui", "click", "open app", "focus app",
                 "move window", "browser tab"),
                ("desktop_", "window_", "browser_", "screen_", "gui_"),
            ),
            (
                ("nmap", "vulnerability", "penetration test", "pentest", "kali", "exploit",
                 "security scan", "scan this target", "bug bounty"),
                ("kali_", "security_", "bugbounty_", "cybersecurity_"),
            ),
            (
                ("remember", "memory", "previous conversation", "saved note", "knowledge graph"),
                ("memory_", "knowledge_", "note_", "session_"),
            ),
            (
                ("robot", "arduino", "mqtt", "ros2", "serial port", "sensor"),
                ("robot_", "mqtt_", "ros2_"),
            ),
            (
                ("play music", "youtube", "local mp3", "recognize this song", "whatsapp"),
                ("browser_play_youtube", "play_local_mp3", "recognize_song", "whatsapp_"),
            ),
            (
                ("schedule", "automation", "remind me", "timer", "event trigger"),
                ("automation_", "schedule_", "event_"),
            ),
        ]

        matching_prefixes: list[str] = []
        for markers, prefixes in categories:
            import re
            if any(re.search(marker, task) for marker in markers):
                matching_prefixes.extend(prefixes)
        if not matching_prefixes:
            # Conversational/explanatory prompts should not send the entire tool
            # catalog to a 27B local model. This materially reduces prompt size
            # and avoids local inference timeouts for ordinary typed questions.
            return []

        selected = [
            tool for tool in tools
            if any(str(tool.get("name", "")).casefold().startswith(prefix) for prefix in matching_prefixes)
        ]
        if len(selected) <= 12:
            return selected

        # For broad requests, put tools whose names overlap the actual task first,
        # and cap the catalog size to reduce local prompt processing time.
        import re
        words = {
            word for word in re.findall(r"[a-z][a-z0-9_]{2,}", task)
            if word not in {"please", "could", "would", "should", "this", "that", "with", "from", "have", "into"}
        }
        def score(tool: dict[str, Any]) -> int:
            name = str(tool.get("name", "")).casefold().replace("_", " ")
            description = str(tool.get("description", "")).casefold()
            return sum(3 for word in words if word in name) + sum(1 for word in words if word in description)
        return sorted(selected, key=score, reverse=True)[:12]

    def _complete_local(
        self,
        prompt: str,
        *,
        instructions: str,
        tool_broker=None,
        allow_action_tools: bool,
        max_tool_rounds: int,
        model_role: str,
    ) -> LLMResponse:
        all_tools = (
            tool_broker.schemas(
                allow_action_tools=allow_action_tools,
                include_confirmation_tools=True,
            )
            if tool_broker is not None else []
        )
        tools = self._select_local_tools(prompt, all_tools)
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
    ) -> LLMResponse:
        online = internet_available()
        _, selected_role = self.selected_model(model_role)
        failures: list[str] = []
        runtime_override = ModelRouter.runtime_override()
        runtime_provider = (runtime_override or {}).get("provider", "")
        provider_order = self.providers.order()
        if runtime_provider in self.providers.CONFIGS:
            provider_order = [runtime_provider] + [
                name for name in provider_order if name != runtime_provider
            ]

        if online:
            for provider in provider_order:
                if not self.providers.available(provider):
                    continue
                runtime_model = (runtime_override or {}).get("model", "")
                model = (
                    runtime_model
                    if runtime_model and (not runtime_provider or provider == runtime_provider)
                    else self.explicit_model or self.providers.model(provider, selected_role)
                )
                try:
                    result = self._complete_online(
                        provider, prompt, instructions=instructions,
                        use_web_search=use_web_search, tool_broker=tool_broker,
                        allow_action_tools=allow_action_tools,
                        max_tool_rounds=max_tool_rounds, model=model,
                        model_role=selected_role,
                    )
                    self.providers.reset(provider)
                    return result
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    failures.append(f"{provider}: {error}")
                    if is_retryable_provider_error(exc):
                        if is_quota_exhausted_provider_error(exc):
                            try:
                                quota_cooldown = float(
                                    os.getenv("JENEFAR_PROVIDER_QUOTA_COOLDOWN_SECONDS", "3600")
                                )
                            except ValueError:
                                quota_cooldown = 3600.0
                            self.providers.cooldown(
                                provider, seconds=max(60.0, quota_cooldown)
                            )
                        else:
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
            )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
            # Keep full diagnostics in the terminal/logs, but do not make the
            # assistant read a giant provider quota traceback aloud to the user.
            print(
                "[JENEFAR] Local model fallback failed after cloud-provider "
                f"failover: {local_error}"
            )
            lowered = local_error.casefold()
            if "timed out" in lowered or "timeout" in lowered:
                message = (
                    "Main abhi jawab generate nahi kar paayi: local Ollama model ne "
                    "time par response nahi diya aur online AI providers bhi unavailable hain. "
                    "Ollama mein model ko direct test karke phir instruction dobara bhejein."
                )
            elif "empty answer" in lowered or "returned an empty" in lowered:
                message = (
                    "Local model ne khaali response diya. Jenefar ne direct-answer mode "
                    "try kiya, lekin is model/API combination se visible answer nahi mila."
                )
            else:
                message = (
                    "Abhi online providers aur local AI dono se response nahi mil paaya. "
                    "Technical detail terminal mein [JENEFAR] Local model fallback failed ke neeche hai."
                )
            return LLMResponse(
                message,
                "offline_unavailable",
                model_role=selected_role,
            )
