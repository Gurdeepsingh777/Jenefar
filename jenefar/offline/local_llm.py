from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
import time

from jenefar.core.model_router import ModelRouter


@dataclass
class LocalModelInfo:
    base_url: str
    model: str


class LocalLLMClient:
    """OpenAI-compatible local chat-completions client with role-aware models."""

    def __init__(self, model_role: str | None = None) -> None:
        self.base_url = os.getenv(
            "JENEFAR_LOCAL_LLM_BASE_URL",
            "http://127.0.0.1:11434/v1",
        ).rstrip("/")
        self.model_role = (model_role or "fast").strip().lower()
        role_env = ModelRouter().local_model_env(self.model_role)
        self.timeout_seconds = min(max(float(os.getenv("JENEFAR_LOCAL_LLM_TIMEOUT_SECONDS", "45")), 5.0), 300.0)
        self.model = (
            os.getenv(role_env, "").strip()
            or os.getenv("JENEFAR_LOCAL_LLM_MODEL", "").strip()
        )

    def _get_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Jenefar/1.0"},
        )
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return json.loads(response.read().decode("utf-8"))

    def detect(self, model_role: str | None = None) -> LocalModelInfo | None:
        if model_role:
            self.model_role = model_role.strip().lower()
            role_env = ModelRouter().local_model_env(self.model_role)
            self.model = (
                os.getenv(role_env, "").strip()
                or os.getenv("JENEFAR_LOCAL_LLM_MODEL", "").strip()
            )

        bases = [self.base_url]
        if self.base_url == "http://127.0.0.1:11434/v1":
            bases.extend([
                "http://127.0.0.1:8080/v1",
                "http://127.0.0.1:8000/v1",
            ])

        for base in bases:
            try:
                payload = self._get_json(f"{base}/models")
                models = payload.get("data") or []
                model = self.model or (str(models[0].get("id")) if models else "")
                if model:
                    return LocalModelInfo(base, model)
            except Exception:
                continue
        return None

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for tool in tools or []:
            if tool.get("type") != "function":
                continue
            converted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters") or {},
                },
            })
        return converted

    def complete(
        self,
        *,
        prompt: str,
        instructions: str,
        tools: list[dict[str, Any]] | None = None,
        tool_broker=None,
        max_tool_rounds: int = 4,
        model_role: str | None = None,
        deadline: float | None = None,
    ) -> tuple[str, list[dict[str, str]]]:
        info = self.detect(model_role=model_role)
        if info is None:
            raise RuntimeError(
                "No local LLM server detected. Start Ollama or llama.cpp and install a local model."
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ]
        local_tools = self._convert_tools(tools)

        for _ in range(max(1, min(max_tool_rounds, 20))):
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Jenefar execution budget exhausted")
            else:
                remaining = None
            payload: dict[str, Any] = {
                "model": info.model,
                "messages": messages,
                "stream": False,
            }
            if local_tools:
                payload["tools"] = local_tools
                payload["tool_choice"] = "auto"

            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{info.base_url}/chat/completions",
                method="POST",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer sk-local",
                },
            )
            try:
                request_timeout = self.timeout_seconds if remaining is None else min(self.timeout_seconds, max(0.5, remaining))
                with urllib.request.urlopen(request, timeout=request_timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError) as exc:
                raise RuntimeError(f"Local LLM request failed: {exc}") from exc

            choice = (result.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                return str(message.get("content") or "Local model returned no text."), []

            messages.append(message)
            pending_tools: list[dict[str, str]] = []
            if tool_broker is None:
                return (
                    "Local model requested a tool, but no local tool broker is available.",
                    pending_tools,
                )

            for call in tool_calls:
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                arguments_raw = function.get("arguments") or "{}"
                try:
                    arguments = json.loads(arguments_raw)
                except json.JSONDecodeError:
                    arguments = {}

                output = tool_broker.invoke(name, arguments)
                parsed: dict[str, Any]
                try:
                    parsed = json.loads(output)
                except json.JSONDecodeError:
                    parsed = {"result": output}

                if parsed.get("status") == "approval_required":
                    pending_tools.append({
                        "pending_id": str(parsed.get("pending_id") or ""),
                        "tool": name,
                        "call_id": str(call.get("id") or ""),
                    })

                messages.append({
                    "role": "tool",
                    "tool_call_id": str(call.get("id") or ""),
                    "name": name,
                    "content": output,
                })

            if pending_tools:
                ids = ", ".join(item["pending_id"] for item in pending_tools if item["pending_id"])
                return (
                    "A local tool requested explicit confirmation before execution."
                    + (f" Pending approval id(s): {ids}." if ids else ""),
                    pending_tools,
                )

        return "The local tool loop reached its safety limit.", []
