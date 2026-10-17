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


def test_quota_exhaustion_is_distinguished_from_ordinary_rate_limit():
    from jenefar.core.provider_pool import is_quota_exhausted_provider_error

    assert is_quota_exhausted_provider_error(
        RuntimeError("429 insufficient_quota credit_balance_exhausted")
    )
    assert is_quota_exhausted_provider_error(
        RuntimeError("RESOURCE_EXHAUSTED: You exceeded your current quota")
    )
    assert not is_quota_exhausted_provider_error(
        RuntimeError("429 rate limit reached; retry in 5 seconds")
    )


def test_llm_uses_longer_cooldown_for_exhausted_provider_quota(monkeypatch):
    from jenefar.core.llm import LLMClient

    monkeypatch.setenv("JENEFAR_PROVIDER_QUOTA_COOLDOWN_SECONDS", "7200")
    monkeypatch.setattr("jenefar.core.llm.internet_available", lambda: True)
    client = LLMClient()
    monkeypatch.setattr(client.providers, "order", lambda: ["gemini"])
    monkeypatch.setattr(client.providers, "available", lambda _provider: True)
    monkeypatch.setattr(client.providers, "model", lambda _provider, _role: "online-model")
    cooldowns = []
    monkeypatch.setattr(
        client.providers,
        "cooldown",
        lambda provider, seconds=None: cooldowns.append((provider, seconds)),
    )
    monkeypatch.setattr(
        client,
        "_complete_online",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("429 insufficient_quota credit_balance_exhausted")
        ),
    )
    monkeypatch.setattr(
        client,
        "_complete_local",
        lambda *_args, **_kwargs: __import__(
            "jenefar.core.llm", fromlist=["LLMResponse"]
        ).LLMResponse("Offline answer", "local"),
    )

    result = client.complete("Test quota fallback")

    assert result.provider == "local"
    assert cooldowns == [("gemini", 7200.0)]


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
