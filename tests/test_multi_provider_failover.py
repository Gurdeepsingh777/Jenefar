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


def test_complete_hides_raw_provider_dump(monkeypatch):
    from jenefar.core.llm import LLMClient, LLMResponse

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    monkeypatch.delenv("JENEFAR_DISABLE_LOCAL_FALLBACK", raising=False)

    client = LLMClient.__new__(LLMClient)
    client.explicit_model = None
    client.default_role = "fast"
    client.providers = ProviderPool()
    client.local = type("Local", (), {"model": "local-test"})()

    def boom_online(self, provider, *args, **kwargs):
        if provider == "openai":
            exc = Exception(
                "Error code: 429 - {'error': {'message': 'You have no credits remaining. "
                "Add credits at https://platform.openai.com/settings/organization/billing/.', "
                "'code': 'credit_balance_exhausted'}}"
            )
            exc.status_code = 429
            raise exc
        if provider == "gemini":
            exc = Exception(
                "Error code: 400 - Function call is missing a thought_signature in functionCall parts."
            )
            exc.status_code = 400
            raise exc
        raise Exception("provider down")

    def boom_local(self, *args, **kwargs):
        raise RuntimeError("Local LLM request failed: timed out")

    monkeypatch.setattr("jenefar.core.llm.internet_available", lambda: True)
    monkeypatch.setattr(LLMClient, "selected_model", lambda self, role=None: ("x", "fast"))
    monkeypatch.setattr(LLMClient, "_complete_online", boom_online)
    monkeypatch.setattr(LLMClient, "_complete_local", boom_local)

    result = LLMClient.complete(client, "scan my network")
    assert isinstance(result, LLMResponse)
    text = result.text.lower()
    assert "platform.openai.com" not in text
    assert "thought_signature" not in text
    assert "credit_balance_exhausted" not in text
    assert "error code: 429" not in text
    assert "unavailable" in text or "credits" in text or "timeout" in text


def test_retryable_errors():
    class RateLimitError(Exception):
        status_code = 429

    class BadRequest(Exception):
        status_code = 400

    assert is_retryable_provider_error(RateLimitError("rate limit"))
    assert is_retryable_provider_error(Exception("AuthenticationError: invalid api key"))
    assert is_retryable_provider_error(Exception("connection timeout"))
    assert not is_retryable_provider_error(BadRequest("bad request"))
