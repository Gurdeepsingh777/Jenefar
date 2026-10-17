from __future__ import annotations

import os

from jenefar.core.provider_pool import ProviderPool, is_retryable_provider_error


def test_provider_order_and_configuration(monkeypatch):
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openrouter,gemini,groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    pool = ProviderPool()
    assert pool.order() == ["openrouter", "gemini", "groq"]
    assert pool.configured("openrouter")
    assert pool.configured("gemini")
    assert not pool.configured("groq")


def test_provider_cooldown(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    pool = ProviderPool()
    assert pool.available("openrouter")
    pool.cooldown("openrouter", seconds=60)
    assert not pool.available("openrouter")
    pool.reset("openrouter")
    assert pool.available("openrouter")


def test_retryable_errors():
    class RateLimitError(Exception):
        status_code = 429

    class BadRequest(Exception):
        status_code = 400

    assert is_retryable_provider_error(RateLimitError("rate limit"))
    assert is_retryable_provider_error(Exception("AuthenticationError: invalid api key"))
    assert is_retryable_provider_error(Exception("connection timeout"))
    assert not is_retryable_provider_error(BadRequest("bad request"))


def test_generic_telegram_gemini_key_is_usable_by_avatar_llm(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "generic-gemini-key")
    monkeypatch.setenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    monkeypatch.setenv("LLM_MODEL_NAME", "gemini-3.8-flash")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("JENEFAR_GEMINI_MODEL_FAST", raising=False)

    pool = ProviderPool()
    assert pool.configured("gemini")
    assert pool.api_key("gemini") == "generic-gemini-key"
    assert pool.model("gemini", "fast") == "gemini-3.8-flash"
