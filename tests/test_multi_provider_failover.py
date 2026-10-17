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



def test_default_provider_order_prioritizes_free_friendly_providers(monkeypatch):
    monkeypatch.delenv("JENEFAR_PROVIDER_ORDER", raising=False)
    assert ProviderPool().order() == ["groq", "gemini", "openrouter", "openai"]


def test_legacy_example_orders_migrate_but_custom_order_is_preserved(monkeypatch):
    pool = ProviderPool()
    for old_order in (
        "openai,openrouter,gemini,groq",
        "gemini,openrouter,groq,openai",
    ):
        monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", old_order)
        assert pool.order() == ["groq", "gemini", "openrouter", "openai"]

    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openrouter,groq")
    assert pool.order() == ["openrouter", "groq"]


def test_daily_and_free_tier_quota_errors_get_long_cooldown_classification():
    from jenefar.core.provider_pool import is_quota_exhausted_provider_error

    assert is_quota_exhausted_provider_error(
        RuntimeError("Daily limit reached; try again tomorrow")
    )
    assert is_quota_exhausted_provider_error(
        RuntimeError("Free tier requests per day quota exhausted")
    )
    assert not is_quota_exhausted_provider_error(
        RuntimeError("429 rate limit reached; retry in 5 seconds")
    )


def test_default_route_fails_over_groq_gemini_to_openrouter_before_local(monkeypatch, capsys):
    from jenefar.core.llm import LLMClient, LLMResponse

    monkeypatch.delenv("JENEFAR_PROVIDER_ORDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("JENEFAR_PROVIDER_QUOTA_COOLDOWN_SECONDS", "3600")
    monkeypatch.setattr("jenefar.core.llm.internet_available", lambda: True)

    client = LLMClient()
    attempted = []

    def fake_online(provider, *_args, **kwargs):
        attempted.append(provider)
        if provider in {"groq", "gemini"}:
            raise RuntimeError("429 RESOURCE_EXHAUSTED: daily quota exceeded")
        if provider == "openrouter":
            return LLMResponse(
                "OpenRouter free route response",
                provider,
                model=kwargs["model"],
                model_role=kwargs["model_role"],
            )
        raise AssertionError(f"Unexpected provider was attempted: {provider}")

    monkeypatch.setattr(client, "_complete_online", fake_online)
    monkeypatch.setattr(
        client,
        "_complete_local",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Local fallback should not run while OpenRouter succeeds")
        ),
    )

    result = client.complete("Reply with a simple test response.")

    assert attempted == ["groq", "gemini", "openrouter"]
    assert result.provider == "openrouter"
    assert result.text == "OpenRouter free route response"
    output = capsys.readouterr().out
    assert "Online LLM provider groq/openai/gpt-oss-120b failed" in output
    assert "quota exhausted" in output
    assert "Online LLM provider gemini/online-model failed" in output
