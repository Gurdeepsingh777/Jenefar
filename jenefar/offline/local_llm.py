from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from typing import Any

from jenefar.core.model_router import ModelRouter


@dataclass
class LocalModelInfo:
    base_url: str
    model: str
    api: str = "openai"


class LocalLLMClient:
    """Role-aware local chat client for Ollama or any OpenAI-compatible server.

    In auto mode, a local Ollama server is detected through /api/tags and uses
    its native /api/chat endpoint. Other local servers continue to use
    /v1/models and /v1/chat/completions. Both paths support the same Jenefar
    tool broker, skill context, memory, and approval flow.
    """

    def __init__(self, model_role: str | None = None) -> None:
        self.base_url = os.getenv(
            "JENEFAR_LOCAL_LLM_BASE_URL",
            "http://127.0.0.1:11434/v1",
        ).rstrip("/")
        self.api = os.getenv("JENEFAR_LOCAL_LLM_API", "auto").strip().lower() or "auto"
        if self.api not in {"auto", "ollama", "openai"}:
            self.api = "auto"
        self.model_role = (model_role or "fast").strip().lower()
        self.model = self._configured_model(self.model_role)
        self._last_detection_error = ""

    @staticmethod
    def _configured_model(role: str) -> str:
        role_env = ModelRouter().local_model_env(role)
        return os.getenv(role_env, "").strip() or os.getenv("JENEFAR_LOCAL_LLM_MODEL", "").strip()

    @staticmethod
    def _origin(base: str) -> str:
        value = str(base or "").strip().rstrip("/")
        if value.endswith("/v1"):
            value = value[:-3].rstrip("/")
        elif value.endswith("/api"):
            value = value[:-4].rstrip("/")
        return value

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            cleaned = str(value or "").rstrip("/")
            if cleaned and cleaned not in result:
                result.append(cleaned)
        return result

    def _openai_bases(self) -> list[str]:
        base = self.base_url
        if not base.endswith("/v1"):
            base += "/v1"
        values = [base]
        if self._origin(self.base_url) in {
            "http://127.0.0.1:11434",
            "http://localhost:11434",
        }:
            values.extend([
                "http://127.0.0.1:8080/v1",
                "http://127.0.0.1:8000/v1",
            ])
        return self._unique(values)

    def _ollama_origins(self) -> list[str]:
        origin = self._origin(self.base_url)
        values = [origin]
        parsed = urlsplit(origin)
        if parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port in {None, 11434}:
            values.extend(["http://127.0.0.1:11434", "http://localhost:11434"])
        return self._unique(values)

    @staticmethod
    def _get_json(url: str, *, timeout: float = 3.0) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "Jenefar/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(800).decode("utf-8", errors="replace").strip()
            except Exception:
                pass
            raise RuntimeError(
                f"HTTP {exc.code} from {url}" + (f": {detail}" if detail else "")
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid JSON object from {url}.")
        return payload

    @staticmethod
    def _installed_names(records: Any, *, ollama: bool) -> list[str]:
        if not isinstance(records, list):
            return []
        values: list[str] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            raw = item.get("name") or item.get("model") if ollama else item.get("id")
            model = str(raw or "").strip()
            if model and model not in values:
                values.append(model)
        return values

    def _select_installed_model(self, names: list[str], api: str) -> str:
        configured = self.model
        if configured and configured in names:
            return configured
        if configured and names:
            # Avoid repeatedly using a stale model ID that the local server does
            # not have. Prefer an installed model and log the selection clearly.
            print(
                f"[JENEFAR] Configured local model '{configured}' is not listed by the "
                f"{api} server; using installed model '{names[0]}'. "
                "Set JENEFAR_LOCAL_LLM_MODEL to pin a different installed model."
            )
        return names[0] if names else configured

    def _detect_ollama(self) -> LocalModelInfo | None:
        last_error = ""
        for origin in self._ollama_origins():
            try:
                payload = self._get_json(f"{origin}/api/tags")
                names = self._installed_names(payload.get("models"), ollama=True)
                if not names:
                    last_error = f"{origin}/api/tags returned no installed Ollama models."
                    continue
                selected = self._select_installed_model(names, "Ollama")
                if selected:
                    return LocalModelInfo(origin, selected, "ollama")
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        if last_error:
            self._last_detection_error = last_error
        return None

    def detect(self, model_role: str | None = None) -> LocalModelInfo | None:
        if model_role:
            self.model_role = model_role.strip().lower()
            self.model = self._configured_model(self.model_role)
        self._last_detection_error = ""

        parsed = urlsplit(self._origin(self.base_url))
        is_ollama_host = parsed.port == 11434 or parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port is None

        if self.api in {"auto", "ollama"} and (self.api == "ollama" or is_ollama_host):
            info = self._detect_ollama()
            if info:
                self.model = info.model
                return info
            if self.api == "ollama":
                return None

        if self.api != "ollama":
            last_error = ""
            for base in self._openai_bases():
                try:
                    payload = self._get_json(f"{base}/models")
                    names = self._installed_names(payload.get("data"), ollama=False)
                    selected = self._select_installed_model(names, "OpenAI-compatible local")
                    if selected:
                        self.model = selected
                        return LocalModelInfo(base, selected, "openai")
                    last_error = f"{base}/models returned no model IDs."
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
            if last_error:
                self._last_detection_error = last_error

        # An explicitly configured Ollama API can be used on a non-default port.
        if self.api == "auto" and not is_ollama_host:
            info = self._detect_ollama()
            if info:
                self.model = info.model
                return info
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

    @staticmethod
    def _tool_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                value = json.loads(raw or "{}")
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _request_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            method="POST",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer sk-local",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(1000).decode("utf-8", errors="replace").strip()
            except Exception:
                pass
            raise RuntimeError(
                f"HTTP {exc.code} from local LLM endpoint {url}"
                + (f": {detail}" if detail else "")
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Could not reach local LLM endpoint {url}: {exc}") from exc
        if not isinstance(result, dict):
            raise RuntimeError(f"Local LLM endpoint {url} returned invalid JSON.")
        if result.get("error"):
            raise RuntimeError(f"Local LLM endpoint error: {result['error']}")
        return result

    @staticmethod
    def _is_chat_route_not_found(exc: Exception) -> bool:
        """Distinguish an unsupported chat URL from a missing model tag."""
        message = str(exc).lower()
        has_404 = any(marker in message for marker in (
            "http 404 from local llm endpoint",
            "http error 404",
            "404 not found",
            "404 page not found",
        ))
        if not has_404:
            return False
        return not any(marker in message for marker in (
            "model not found",
            "model does not exist",
            "model is not found",
            "no such model",
        ))

    def _request_chat_with_fallback(
        self,
        info: LocalModelInfo,
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> tuple[dict[str, Any], LocalModelInfo]:
        """Try the detected chat endpoint, then the alternate local protocol on route 404."""
        endpoint = (
            f"{info.base_url}/api/chat"
            if info.api == "ollama"
            else f"{info.base_url}/chat/completions"
        )
        try:
            return self._request_json(endpoint, payload, timeout=timeout), info
        except RuntimeError as primary_error:
            if self.api != "auto" or not self._is_chat_route_not_found(primary_error):
                raise

        origin = self._origin(info.base_url)
        if info.api == "ollama":
            alternate = LocalModelInfo(f"{origin}/v1", info.model, "openai")
            alternate_endpoint = f"{alternate.base_url}/chat/completions"
        else:
            alternate = LocalModelInfo(origin, info.model, "ollama")
            alternate_endpoint = f"{alternate.base_url}/api/chat"

        try:
            result = self._request_json(alternate_endpoint, payload, timeout=timeout)
        except Exception as alternate_error:
            raise RuntimeError(
                "Local chat endpoint returned 404 and the alternate local protocol also failed. "
                f"Detected protocol: {info.api}; primary endpoint: {endpoint}; "
                f"alternate endpoint: {alternate_endpoint}; alternate error: "
                f"{type(alternate_error).__name__}: {alternate_error}"
            ) from alternate_error

        info.api = alternate.api
        info.base_url = alternate.base_url
        self.model = info.model
        print(
            f"[JENEFAR] Local LLM endpoint returned 404; switched to "
            f"{info.api} chat API at {info.base_url}."
        )
        return result, info

    def complete(
        self,
        *,
        prompt: str,
        instructions: str,
        tools: list[dict[str, Any]] | None = None,
        tool_broker=None,
        max_tool_rounds: int = 4,
        model_role: str | None = None,
    ) -> tuple[str, list[dict[str, str]]]:
        info = self.detect(model_role=model_role)
        if info is None:
            detail = f" Last diagnostic: {self._last_detection_error}" if self._last_detection_error else ""
            raise RuntimeError(
                "No compatible local LLM server/model detected. Start the model server and "
                "verify JENEFAR_LOCAL_LLM_BASE_URL and JENEFAR_LOCAL_LLM_MODEL."
                + detail
            )

        print(f"[JENEFAR] Local LLM active: {info.api}/{info.model} ({info.base_url}).")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ]
        local_tools = self._convert_tools(tools)

        for _ in range(max(1, min(max_tool_rounds, 20))):
            payload: dict[str, Any] = {
                "model": info.model,
                "messages": messages,
                "stream": False,
            }
            if local_tools:
                payload["tools"] = local_tools
                if info.api == "openai":
                    payload["tool_choice"] = "auto"

            timeout = float(os.getenv("JENEFAR_LOCAL_LLM_TIMEOUT_SECONDS", "240"))
            result, info = self._request_chat_with_fallback(
                info, payload, timeout=timeout
            )
            if info.api == "ollama":
                message = result.get("message") or {}
            else:
                choice = (result.get("choices") or [{}])[0]
                message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                answer = str(message.get("content") or "").strip()
                if not answer:
                    raise RuntimeError(
                        "Local model returned an empty answer. Check whether the selected "
                        "model supports chat completion, or choose a chat/instruct model."
                    )
                return answer, []

            if info.api == "ollama":
                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": str(message.get("content") or ""),
                    "tool_calls": [],
                }
                for call in tool_calls:
                    function = call.get("function") or {}
                    assistant_message["tool_calls"].append({
                        "function": {
                            "name": str(function.get("name") or ""),
                            "arguments": self._tool_arguments(function.get("arguments")),
                        }
                    })
                messages.append(assistant_message)
            else:
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
                arguments = self._tool_arguments(function.get("arguments"))
                if not name:
                    raise RuntimeError("Local model returned a tool call without a function name.")

                output = tool_broker.invoke(name, arguments)
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

                if info.api == "ollama":
                    messages.append({
                        "role": "tool",
                        "tool_name": name,
                        "content": output,
                    })
                else:
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
