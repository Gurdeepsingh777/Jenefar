from __future__ import annotations

import os
import time
from dataclasses import dataclass


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
            "gemini-2.5-flash-lite",
        ),
        "groq": ProviderConfig(
            "groq",
            "GROQ_API_KEY",
            "https://api.groq.com/openai/v1",
            "GROQ_MODEL",
            "llama-3.3-70b-versatile",
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

    def order(self) -> list[str]:
        raw = os.getenv(
            "JENEFAR_PROVIDER_ORDER",
            "openai,openrouter,gemini,groq,cerebras",
        )
        names = [item.strip().lower() for item in raw.split(",") if item.strip()]
        valid = [name for name in names if name in self.CONFIGS]
        return valid or ["openai"]

    def configured(self, name: str) -> bool:
        config = self.CONFIGS[name]
        return bool(os.getenv(config.api_key_env, "").strip())

    def model(self, name: str, role: str = "fast") -> str:
        config = self.CONFIGS[name]
        role_env = f"JENEFAR_{name.upper()}_MODEL_{(role or 'fast').strip().upper()}"
        return (
            os.getenv(role_env, "").strip()
            or os.getenv(config.model_env, "").strip()
            or config.default_model
        )

    def available(self, name: str) -> bool:
        return self.configured(name) and time.monotonic() >= self.cooldowns.get(name, 0.0)

    def cooldown(self, name: str, seconds: float | None = None) -> None:
        if seconds is None:
            seconds = float(os.getenv("JENEFAR_PROVIDER_COOLDOWN_SECONDS", "60"))
        self.cooldowns[name] = time.monotonic() + max(1.0, seconds)

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
            }
        return result


def is_retryable_provider_error(exc: Exception) -> bool:
    """Classify provider failures that should permit automatic failover."""
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


__all__ = ["ProviderConfig", "ProviderPool", "is_retryable_provider_error"]
