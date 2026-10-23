from __future__ import annotations

import os
import time
from dataclasses import dataclass

from jenefar.core.model_ids import normalize_model_id


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key_env: str
    base_url: str
    model_env: str
    default_model: str


class ProviderPool:
    """Online LLM provider registry with bounded per-process cooldowns."""

    CONFIGS = {
        "openai": ProviderConfig("openai", "OPENAI_API_KEY", "", "OPENAI_MODEL", "gpt-5.6-luna"),
        "apinex": ProviderConfig(
            "apinex",
            "APINEX_API_KEY",
            "https://api.apinex.bond/v1",
            "APINEX_MODEL",
            "free/gpt-6-luna",
        ),
        "openrouter": ProviderConfig(
            "openrouter",
            "OPENROUTER_API_KEY",
            "https://openrouter.ai/api/v1",
            "OPENROUTER_MODEL",
            "openrouter/free",
        ),
        "gemini": ProviderConfig(
            "gemini",
            "GEMINI_API_KEY",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "GEMINI_MODEL",
            "gemini-3.5-flash-lite",
        ),
        "groq": ProviderConfig(
            "groq",
            "GROQ_API_KEY",
            "https://api.groq.com/openai/v1",
            "GROQ_MODEL",
            "openai/gpt-oss-120b",
        ),
        "cerebras": ProviderConfig(
            "cerebras",
            "CEREBRAS_API_KEY",
            "https://api.cerebras.ai/v1",
            "CEREBRAS_MODEL",
            "gpt-oss-120b",
        ),
    }

    def __init__(self) -> None:
        self.cooldowns: dict[str, float] = {}
        self.latency_samples: dict[str, list[float]] = {name: [] for name in self.CONFIGS}
        self.failure_samples: dict[str, int] = {name: 0 for name in self.CONFIGS}

    def order(self) -> list[str]:
        # Prefer providers with useful free tiers, then optionally use OpenAI
        # if the user has configured a working paid key. Local Ollama is the
        # automatic final fallback in LLMClient.complete().
        default_order = ["groq", "gemini", "openrouter", "apinex", "openai"]
        raw = os.getenv("JENEFAR_PROVIDER_ORDER", "").strip()
        if not raw:
            return default_order

        names = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
        # Migrate the old sample orders automatically: many existing .env files
        # were created from an older .env.example and otherwise keep the old
        # cloud-provider priority forever. Explicit custom orders are preserved.
        legacy_defaults = {
            ("openai", "openrouter", "gemini", "groq"),
            ("gemini", "openrouter", "groq", "openai"),
        }
        if names in legacy_defaults:
            return default_order

        valid = list(dict.fromkeys(name for name in names if name in self.CONFIGS))
        return valid or default_order

    def order_for_role(self, role: str = "fast") -> list[str]:
        """Prefer providers with a proven lower latency after a bounded warm-up."""
        names = self.order()
        enabled = os.getenv("JENEFAR_ADAPTIVE_ROUTING", "1").strip().lower() not in {"0", "false", "no", "off"}
        if not enabled:
            return names
        try:
            warmup = max(1, min(20, int(os.getenv("JENEFAR_ROUTING_WARMUP_SAMPLES", "2"))))
        except ValueError:
            warmup = 2
        known = {name: samples for name, samples in self.latency_samples.items() if name in names and len(samples) >= warmup}
        if not known:
            return names
        position = {name: index for index, name in enumerate(names)}
        def score(name: str) -> tuple[float, int]:
            samples = known.get(name)
            if not samples:
                return (float("inf"), position[name])
            recent = samples[-8:]
            average = sum(recent) / len(recent)
            failures = self.failure_samples.get(name, 0)
            return (average * (1.0 + min(2.0, failures / max(1, len(samples)))), position[name])
        return sorted(names, key=score)

    def record_latency(self, name: str, elapsed_seconds: float, *, success: bool) -> None:
        if name not in self.CONFIGS:
            return
        samples = self.latency_samples[name]
        samples.append(max(0.0, float(elapsed_seconds)))
        del samples[:-8]
        if not success:
            self.failure_samples[name] += 1

    def latency_status(self) -> dict[str, dict]:
        result = {}
        for name in self.CONFIGS:
            samples = self.latency_samples.get(name, [])
            result[name] = {
                "samples": len(samples),
                "average_ms": round(sum(samples) / len(samples) * 1000, 1) if samples else None,
                "last_ms": round(samples[-1] * 1000, 1) if samples else None,
                "failures": self.failure_samples.get(name, 0),
            }
        return result

    @staticmethod
    def _generic_gemini_key() -> str:
        base_url = (
            os.getenv("LLM_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
        ).lower()
        if "generativelanguage.googleapis.com" not in base_url:
            return ""
        return os.getenv("LLM_API_KEY", "").strip() or os.getenv("API_KEY", "").strip()

    def configured(self, name: str) -> bool:
        config = self.CONFIGS[name]
        key = os.getenv(config.api_key_env, "").strip()
        if key:
            if name == "openai" and key.startswith("sk-or-"):
                return False
            return True
        if name == "gemini" and self._generic_gemini_key():
            return True
        # Backward compatibility: the existing Jenefar setup may have stored an
        # OpenRouter key in OPENAI_API_KEY before provider-aware routing existed.
        return name == "openrouter" and os.getenv("OPENAI_API_KEY", "").strip().startswith("sk-or-")

    def model(self, name: str, role: str = "fast") -> str:
        config = self.CONFIGS[name]
        role_env = f"JENEFAR_{name.upper()}_MODEL_{(role or 'fast').strip().upper()}"
        selected = (
            os.getenv(role_env, "").strip()
            or os.getenv(config.model_env, "").strip()
            or (
                os.getenv("LLM_MODEL_NAME", "").strip()
                if name == "gemini" and self._generic_gemini_key()
                else ""
            )
            or config.default_model
        )
        if name == "gemini" and selected in {"gemini-2.5-flash-lite", "models/gemini-2.5-flash-lite"}:
            selected = "gemini-3.5-flash-lite"
        return normalize_model_id(selected, name)

    def available(self, name: str) -> bool:
        return self.configured(name) and time.monotonic() >= self.cooldowns.get(name, 0.0)

    def cooldown(self, name: str, seconds: float | None = None) -> None:
        if seconds is None:
            seconds = float(os.getenv("JENEFAR_PROVIDER_COOLDOWN_SECONDS", "60"))
        self.cooldowns[name] = time.monotonic() + max(1.0, seconds)

    def api_key(self, name: str) -> str:
        config = self.CONFIGS[name]
        key = os.getenv(config.api_key_env, "").strip()
        if key:
            return key
        if name == "openrouter":
            legacy = os.getenv("OPENAI_API_KEY", "").strip()
            if legacy.startswith("sk-or-"):
                return legacy
        if name == "gemini":
            return self._generic_gemini_key()
        return ""

    def reset(self, name: str) -> None:
        self.cooldowns.pop(name, None)

    def status(self, role: str = "fast") -> dict[str, dict]:
        now = time.monotonic()
        result = {}
        for name, config in self.CONFIGS.items():
            until = self.cooldowns.get(name, 0.0)
            result[name] = {
                "configured": self.configured(name),
                "available": self.available(name),
                "api_key_env": config.api_key_env,
                "model": self.model(name, role),
                "base_url": config.base_url or "https://api.openai.com/v1",
                "cooldown_seconds": max(0, round(until - now, 1)),
                "latency": self.latency_status()[name],
            }
        return result


def is_quota_exhausted_provider_error(exc: Exception) -> bool:
    """Return True for exhausted provider quotas/credits, not ordinary rate limits."""
    message = str(exc).lower()
    markers = (
        "insufficient_quota",
        "credit_balance_exhausted",
        "exceeded your current quota",
        "quota exceeded",
        "resource_exhausted",
        "billing hard limit",
        "billing_limit",
        "exhausted quota",
        "daily limit",
        "daily quota",
        "daily cap",
        "limit for today",
        "try again tomorrow",
        "requests per day",
        "requests/day",
        "tokens per day",
        "free tier limit",
        "free tier quota",
    )
    return any(marker in message for marker in markers)


def is_retryable_provider_error(exc: Exception) -> bool:
    """Classify provider failures that should permit automatic failover."""
    if is_quota_exhausted_provider_error(exc):
        return True
    message = str(exc).lower()
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)

    if status in {400, 404}:
        return False
    if status in {401, 403, 408, 409, 429, 500, 502, 503, 504}:
        return True

    retry_markers = (
        "authenticationerror",
        "invalid_api_key",
        "rate limit",
        "ratelimit",
        "too many requests",
        "timeout",
        "timed out",
        "connection",
        "service unavailable",
        "temporarily unavailable",
        "internal server error",
        "bad gateway",
    )
    return any(marker in message for marker in retry_markers)


__all__ = ["ProviderConfig", "ProviderPool", "is_quota_exhausted_provider_error", "is_retryable_provider_error"]
