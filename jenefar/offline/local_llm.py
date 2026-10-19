from __future__ import annotations

import json
import os
import time
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from typing import Any

from jenefar.core.model_router import ModelRouter


_ACTIVE_OLLAMA_MODELS: set[tuple[str, str]] = set()
_ACTIVE_OLLAMA_MODELS_LOCK = threading.Lock()


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
        self._runtime_fallback_model = ""
        self.timeout_seconds = float(self._bounded_int_env("JENEFAR_LOCAL_LLM_TIMEOUT_SECONDS", 600, 15, 900))
        self._prefer_compact_requests = False

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
        # After a timeout fallback works, remember it for the rest of this client
        # lifetime. Otherwise every new prompt would waste another primary timeout
        # on the already-slow large model.
        if self._runtime_fallback_model and self._runtime_fallback_model in names:
            return self._runtime_fallback_model
        configured = self.model
        if configured and configured in names:
            # Respect explicit model pins when there is enough available RAM.
            # A large pinned model is not viable on a memory-starved host, though;
            # prefer an already-installed smaller model before it drives the OS
            # into swap or leaves no budget for command execution.
            configured_size = self._model_parameter_billions(configured)
            if configured_size is not None and api.casefold() == "ollama":
                try:
                    import psutil
                    available_gib = float(psutil.virtual_memory().available) / (1024 ** 3)
                except Exception:
                    available_gib = float("inf")
                required_gib = max(3.0, configured_size * 0.65)
                if available_gib < required_gib:
                    candidates = []
                    for name in names:
                        size = self._model_parameter_billions(name)
                        if size is None or size >= configured_size:
                            continue
                        if any(marker in name.casefold() for marker in (
                            "vision", "-vl:", "embed", "rerank", "whisper", "audio",
                        )):
                            continue
                        candidates.append((size, name))
                    if candidates:
                        capacity = max(0.0, available_gib / 0.65)
                        fitting = [item for item in candidates if item[0] <= capacity]
                        selected = max(fitting, key=lambda item: (item[0], item[1].casefold()))[1] if fitting else min(candidates, key=lambda item: (item[0], item[1].casefold()))[1]
                        print(
                            f"[JENEFAR] Local model '{configured}' needs roughly "
                            f"{required_gib:.1f} GiB available RAM; only {available_gib:.1f} GiB "
                            f"is free. Using smaller installed model '{selected}' for this run."
                        )
                        return selected
            return configured
        if configured and names:
            # Avoid repeatedly using a stale model ID that the local server does
            # not have. Prefer a measured-size chat model instead of trusting the
            # arbitrary order returned by /api/tags.
            print(
                f"[JENEFAR] Configured local model '{configured}' is not listed by the "
                f"{api} server; selecting a suitable installed model. "
                "Set JENEFAR_LOCAL_LLM_MODEL to pin a different installed model."
            )

        if not names:
            return configured

        # When no model is pinned, Ollama often returns the largest/last-used
        # model first. Prefer the smallest known-size chat model to reduce RAM
        # pressure and avoid a 27B model exhausting Jenefar's task deadline.
        chat_names = [
            name for name in names
            if not any(marker in name.casefold() for marker in (
                "vision", "-vl:", "embed", "rerank", "whisper", "audio",
            ))
        ] or list(names)
        sized = [
            (size, name)
            for name in chat_names
            if (size := self._model_parameter_billions(name)) is not None
        ]
        if sized:
            sized.sort(key=lambda item: (item[0], item[1].casefold()))
            selected = sized[0][1]
            if not configured:
                print(
                    f"[JENEFAR] No local chat model pinned; selecting the smallest "
                    f"installed model '{selected}' to reduce memory use and response time."
                )
            return selected
        selected = chat_names[0]
        if not configured:
            print(
                f"[JENEFAR] Model sizes were unavailable; using installed model '{selected}'. "
                "Set JENEFAR_LOCAL_LLM_MODEL to pin a model explicitly."
            )
        return selected

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
                    if self.model in names and selected != self.model:
                        previous_size = self._model_parameter_billions(self.model)
                        selected_size = self._model_parameter_billions(selected)
                        if previous_size is not None and selected_size is not None and selected_size < previous_size:
                            # The memory-pressure guard selected a smaller installed
                            # model; unload the oversized model left resident by an
                            # earlier run before the new model starts loading.
                            self._unload_ollama_model(origin, self.model, timeout=1.0)
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
    def _bounded_int_env(name: str, default: int, lower: int, upper: int) -> int:
        try:
            value = int(os.getenv(name, str(default)).strip())
        except (TypeError, ValueError):
            value = default
        return max(lower, min(upper, value))

    @classmethod
    def _ollama_request_options(cls) -> dict[str, Any]:
        think_value = os.getenv("JENEFAR_LOCAL_LLM_THINK", "false").strip().lower()
        keep_alive = os.getenv("JENEFAR_LOCAL_LLM_KEEP_ALIVE", "30s").strip() or "30s"
        num_ctx = cls._bounded_int_env("JENEFAR_LOCAL_LLM_NUM_CTX", 2048, 2048, 65536)
        num_predict = cls._bounded_int_env("JENEFAR_LOCAL_LLM_NUM_PREDICT", 192, 128, 8192)

        # Existing .env files may still contain the old sample defaults (10m,
        # 4096 context, 384 tokens). On a memory-starved machine those legacy
        # settings keep a large model resident and amplify CPU/swap pressure.
        # Preserve custom settings when RAM is healthy, but clamp the old defaults
        # and generation size when less than 8 GiB is currently available.
        try:
            import psutil
            available_gib = float(psutil.virtual_memory().available) / (1024 ** 3)
        except Exception:
            available_gib = None

        if available_gib is not None and available_gib < 8.0:
            keep_alive = "30s"
            num_ctx = min(num_ctx, 2048)
            num_predict = min(num_predict, 192)

        return {
            "think": think_value in {"1", "true", "yes", "on"},
            "keep_alive": keep_alive,
            "options": {
                "num_ctx": num_ctx,
                "num_predict": num_predict,
                "temperature": 0.2,
            },
        }

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        message = str(exc).casefold()
        return any(marker in message for marker in (
            "timed out", "timeout", "read timed out", "socket timeout",
            "urlopen error timed out", "operation timed out",
        ))

    @staticmethod
    def _model_parameter_billions(model: str, details: Any = None) -> float | None:
        import re

        raw = ""
        if isinstance(details, dict):
            raw = str(details.get("parameter_size") or "")
        if not raw:
            raw = str(model or "")
        match = re.search(r"(?<![a-z0-9])([0-9]+(?:\.[0-9]+)?)\s*b(?:illion)?(?![a-z])", raw, re.I)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _find_smaller_ollama_model(self, info: LocalModelInfo) -> LocalModelInfo | None:
        """Select a smaller model only if it is already installed; never pull models automatically."""
        if info.api != "ollama":
            return None
        try:
            payload = self._get_json(f"{self._origin(info.base_url)}/api/tags", timeout=4.0)
        except Exception as exc:
            print(f"[JENEFAR] Could not inspect installed Ollama fallback models: {type(exc).__name__}: {exc}")
            return None

        records = payload.get("models")
        if not isinstance(records, list):
            return None
        current_size = self._model_parameter_billions(info.model)
        candidates: list[tuple[float, str]] = []
        names: set[str] = set()
        for item in records:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name or name == info.model or name in names:
                continue
            names.add(name)
            lowered = name.casefold()
            if any(marker in lowered for marker in ("-vl:", "-vision", "embed", "rerank")):
                continue
            size = self._model_parameter_billions(name, item.get("details"))
            if size is None or (current_size is not None and size >= current_size):
                continue
            candidates.append((size, name))

        if not candidates:
            return None
        # Choose the largest installed model that is still smaller than the
        # timed-out model. This preserves as much response quality as the host
        # can support (e.g. 8B before 4B/1B when falling back from 27B).
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        preferred = os.getenv("JENEFAR_LOCAL_LLM_FALLBACK_MODEL", "").strip()
        chosen = next((name for _size, name in candidates if name == preferred), candidates[0][1])
        return LocalModelInfo(info.base_url, chosen, "ollama")

    @staticmethod
    def _compact_retry_payload(payload: dict[str, Any], info: LocalModelInfo) -> dict[str, Any]:
        """Reduce context/generation pressure once after a local request times out."""
        compact = dict(payload)
        compact["messages"] = [dict(message) for message in payload.get("messages", [])]
        compact["tools"] = payload.get("tools") or []
        if not compact["tools"]:
            # For plain questions only, keep the beginning and end of a very long
            # system prompt so core instructions survive without wasting context.
            for message in compact["messages"]:
                if message.get("role") == "system":
                    content = str(message.get("content") or "")
                    if len(content) > 4200:
                        message["content"] = (
                            content[:3200]
                            + "\n[Middle of long system context omitted for timeout recovery.]\n"
                            + content[-800:]
                        )
                elif message.get("role") == "user":
                    content = str(message.get("content") or "")
                    if len(content) > 8000:
                        message["content"] = (
                            content[:6500]
                            + "\n[Middle of long user input omitted for timeout recovery.]\n"
                            + content[-1000:]
                        )
        if info.api == "ollama":
            compact.update({
                "think": False,
                "keep_alive": os.getenv("JENEFAR_LOCAL_LLM_KEEP_ALIVE", "30s").strip() or "30s",
            })
            options = dict(compact.get("options") or {})
            options["num_ctx"] = min(2048, int(options.get("num_ctx", 2048)))
            options["num_predict"] = min(192, int(options.get("num_predict", 192)))
            options.setdefault("temperature", 0.2)
            compact["options"] = options
            compact.pop("tool_choice", None)
        else:
            compact.pop("think", None)
            compact.pop("keep_alive", None)
            compact.pop("options", None)
            compact["max_tokens"] = min(192, int(compact.get("max_tokens", 192)))
        return compact

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
        model_missing = "model" in message and any(marker in message for marker in (
            "not found",
            "does not exist",
            "no such model",
        ))
        return not model_missing

    @classmethod
    def _remember_ollama_model(cls, info: LocalModelInfo) -> None:
        if info.api != "ollama" or not info.model:
            return
        origin = cls._origin(info.base_url)
        with _ACTIVE_OLLAMA_MODELS_LOCK:
            _ACTIVE_OLLAMA_MODELS.add((origin, info.model))

    @classmethod
    def _unload_ollama_model(
        cls, origin: str, model: str, *, timeout: float = 1.5
    ) -> bool:
        """Ask Ollama to release one model without stopping its shared service."""
        if not origin or not model:
            return False
        url = f"{cls._origin(origin)}/api/generate"
        payload = json.dumps({
            "model": model,
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            method="POST",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=max(0.5, timeout)) as response:
                response.read(2048)
        except Exception as exc:
            print(
                f"[JENEFAR] Could not unload local model {model}: "
                f"{type(exc).__name__}: {exc}"
            )
            return False
        with _ACTIVE_OLLAMA_MODELS_LOCK:
            _ACTIVE_OLLAMA_MODELS.discard((cls._origin(origin), model))
        print(f"[JENEFAR] Released local model from Ollama memory: {model}.")
        return True

    @classmethod
    def release_runtime_models(cls) -> dict[str, Any]:
        """Release only Ollama models this Jenefar process has actually used."""
        with _ACTIVE_OLLAMA_MODELS_LOCK:
            models = sorted(_ACTIVE_OLLAMA_MODELS)
        released = []
        failed = []
        for origin, model in models:
            if cls._unload_ollama_model(origin, model, timeout=2.0):
                released.append(model)
            else:
                failed.append(model)
        return {"attempted": len(models), "released": released, "failed": failed}

    def _request_chat_with_fallback(
        self,
        info: LocalModelInfo,
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> tuple[dict[str, Any], LocalModelInfo]:
        """Try the detected chat endpoint, then the alternate local protocol on route 404."""
        self._remember_ollama_model(info)
        endpoint = (
            f"{info.base_url}/api/chat"
            if info.api == "ollama"
            else f"{info.base_url}/chat/completions"
        )
        try:
            return self._request_json(endpoint, payload, timeout=timeout), info
        except RuntimeError as primary_error:
            # A stale API preference must not strand the local model on a 404.
            # Only switch protocol for a missing route; model-not-found errors are
            # surfaced so detection/configuration can be corrected instead.
            if not self._is_chat_route_not_found(primary_error):
                raise

        origin = self._origin(info.base_url)
        if info.api == "ollama":
            alternate = LocalModelInfo(f"{origin}/v1", info.model, "openai")
            alternate_endpoint = f"{alternate.base_url}/chat/completions"
        else:
            alternate = LocalModelInfo(origin, info.model, "ollama")
            alternate_endpoint = f"{alternate.base_url}/api/chat"

        alternate_payload = dict(payload)
        if alternate.api == "ollama":
            # Add native Ollama controls even when falling back from /v1.
            alternate_payload.update(self._ollama_request_options())
            alternate_payload.pop("tool_choice", None)
        else:
            # Don't leak Ollama-specific request fields into an OpenAI-compatible
            # server if fallback goes in the opposite direction.
            for key in ("think", "keep_alive", "options"):
                alternate_payload.pop(key, None)
            if alternate_payload.get("tools"):
                alternate_payload.setdefault("tool_choice", "auto")

        try:
            result = self._request_json(alternate_endpoint, alternate_payload, timeout=timeout)
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

    def _request_with_timeout_recovery(
        self,
        info: LocalModelInfo,
        payload: dict[str, Any],
        *,
        configured_timeout: float,
    ) -> tuple[dict[str, Any], LocalModelInfo]:
        """Recover from slow local models without exceeding the task's time budget."""
        primary_cap = self._bounded_int_env(
            "JENEFAR_LOCAL_LLM_PRIMARY_TIMEOUT_SECONDS", 25, 5, 300
        )
        retry_cap = self._bounded_int_env(
            "JENEFAR_LOCAL_LLM_RETRY_TIMEOUT_SECONDS", 30, 5, 300
        )
        started_at = time.monotonic()
        total_budget = max(0.0, float(configured_timeout))

        def remaining_budget() -> float:
            return max(0.0, total_budget - (time.monotonic() - started_at))

        def request_with_budget(
            current: LocalModelInfo,
            request_payload: dict[str, Any],
            cap: float,
        ) -> tuple[dict[str, Any], LocalModelInfo]:
            remaining = remaining_budget()
            if remaining < 0.5:
                raise TimeoutError(
                    "Local model recovery stopped because Jenefar's remaining task budget was exhausted."
                )
            return self._request_chat_with_fallback(
                current,
                request_payload,
                timeout=max(0.5, min(remaining, cap)),
            )

        def unload_timed_out_model(current: LocalModelInfo) -> None:
            if current.api == "ollama":
                self._unload_ollama_model(
                    self._origin(current.base_url), current.model, timeout=1.0
                )

        def try_smaller(
            compact_payload: dict[str, Any],
            current: LocalModelInfo,
        ) -> tuple[dict[str, Any], LocalModelInfo] | None:
            smaller = self._find_smaller_ollama_model(current)
            if smaller is None:
                return None
            fallback_payload = dict(compact_payload)
            fallback_payload["model"] = smaller.model
            print(
                f"[JENEFAR] Local model {current.model} timed out; switching to "
                f"already-installed smaller model {smaller.model} within the remaining task budget."
            )
            try:
                result, selected = request_with_budget(smaller, fallback_payload, retry_cap)
            except RuntimeError as exc:
                if not self._is_timeout_error(exc):
                    raise
                raise RuntimeError(
                    f"Both local model '{current.model}' and smaller installed model "
                    f"'{smaller.model}' timed out within the task budget. "
                    "Choose a smaller installed model or increase available RAM. "
                    f"Smaller-model error: {exc}"
                ) from exc
            self._runtime_fallback_model = selected.model
            self.model = selected.model
            self._prefer_compact_requests = True
            return result, selected

        # Give a slow primary model part of the available budget, not all of it.
        # That leaves time to unload it and attempt a smaller, already-installed
        # model before the orchestrator's deadline expires.
        primary_timeout = min(
            float(primary_cap),
            total_budget * 0.55 if total_budget >= 10.0 else total_budget,
        )
        compact_payload = self._compact_retry_payload(payload, info)

        if self._prefer_compact_requests:
            try:
                return request_with_budget(info, compact_payload, retry_cap)
            except RuntimeError as exc:
                if not self._is_timeout_error(exc):
                    raise
                unload_timed_out_model(info)
                smaller_result = try_smaller(compact_payload, info)
                if smaller_result is not None:
                    return smaller_result
                suggestion = (
                    "Install a smaller local model once, for example 'ollama pull qwen3:8b', "
                    "or set JENEFAR_LOCAL_LLM_FALLBACK_MODEL to an already-installed model. "
                    if info.api == "ollama"
                    else "Configure a smaller model in the local server and set its model ID in Jenefar. "
                )
                raise RuntimeError(
                    f"Compact local request to '{info.model}' timed out. {suggestion}"
                    f"Local request error: {exc}"
                ) from exc

        try:
            return request_with_budget(info, payload, primary_timeout)
        except RuntimeError as primary_error:
            if not self._is_timeout_error(primary_error):
                raise

            self._prefer_compact_requests = True
            unload_timed_out_model(info)
            # Refresh the payload using the compact limits before trying another
            # model; this lowers context and RAM pressure after a timeout.
            compact_payload = self._compact_retry_payload(payload, info)
            smaller_result = try_smaller(compact_payload, info)
            if smaller_result is not None:
                return smaller_result

            remaining = remaining_budget()
            if remaining < 0.5:
                raise TimeoutError(
                    f"Local model '{info.model}' timed out and no execution budget remains for a retry."
                ) from primary_error

            print(
                f"[JENEFAR] Local model {info.model} timed out after "
                f"{primary_timeout:g}s; retrying once with compact context "
                f"(remaining budget={remaining:.1f}s, "
                f"tools={'kept' if compact_payload.get('tools') else 'not needed'})."
            )
            try:
                return request_with_budget(info, compact_payload, retry_cap)
            except RuntimeError as retry_error:
                if not self._is_timeout_error(retry_error):
                    raise
                suggestion = (
                    "Install a smaller local model once, for example 'ollama pull qwen3:8b', "
                    "or set JENEFAR_LOCAL_LLM_FALLBACK_MODEL to an already-installed model. "
                    if info.api == "ollama"
                    else "Configure a smaller model in the local server and set its model ID in Jenefar. "
                )
                raise RuntimeError(
                    f"Local model '{info.model}' timed out on normal and compact requests within "
                    f"the {total_budget:g}s local inference budget. {suggestion} "
                    f"Compact retry error: {retry_error}"
                ) from retry_error

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
        cancel_token: Any = None,
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
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Jenefar execution budget exhausted")
            payload: dict[str, Any] = {
                "model": info.model,
                "messages": messages,
                "stream": False,
            }
            if info.api == "ollama":
                # Qwen-family models may spend their generation budget on hidden
                # reasoning and return empty visible content/tool calls. For an
                # assistant runtime, prefer a direct answer unless explicitly
                # opted in to reasoning.
                payload.update(self._ollama_request_options())
            if local_tools:
                payload["tools"] = local_tools
                if info.api == "openai":
                    payload["tool_choice"] = "auto"

            configured_timeout = self.timeout_seconds
            if remaining is not None:
                configured_timeout = min(configured_timeout, max(0.5, remaining))
            result, info = self._request_with_timeout_recovery(
                info,
                payload,
                configured_timeout=configured_timeout,
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

                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                if deadline is not None and deadline <= time.monotonic():
                    raise TimeoutError("Jenefar execution budget exhausted")
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
