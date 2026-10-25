from __future__ import annotations

from jenefar.core.provider_pool import ProviderPool


def test_oxion_provider_configuration_and_default_priority(monkeypatch):
    monkeypatch.setenv("OXION_API_KEY", "cc_test_key")
    monkeypatch.delenv("JENEFAR_PROVIDER_ORDER", raising=False)
    pool = ProviderPool()
    assert pool.configured("oxion")
    assert pool.api_key("oxion") == "cc_test_key"
    assert pool.model("oxion") == "claude-sonnet-5"
    assert pool.CONFIGS["oxion"].base_url == "https://www.oxionai.com/v1"
    assert pool.order()[0] == "oxion"


def test_oxion_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("OXION_MODEL", "deepseek-v4-flash-0731")
    assert ProviderPool().model("oxion") == "deepseek-v4-flash-0731"


def test_oxion_role_specific_model_override(monkeypatch):
    monkeypatch.setenv("JENEFAR_OXION_MODEL_CODING", "qwen3.8-27b")
    assert ProviderPool().model("oxion", "coding") == "qwen3.8-27b"


def test_oxion_missing_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("OXION_API_KEY", raising=False)
    assert not ProviderPool().configured("oxion")
