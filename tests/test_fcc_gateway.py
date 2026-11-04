from __future__ import annotations

import json
from urllib.error import URLError

from jenefar.core import fcc_gateway
from jenefar.core.provider_pool import ProviderPool


def test_fcc_defaults_are_local_and_openai_compatible(monkeypatch):
    monkeypatch.delenv("FCC_BASE_URL", raising=False)
    monkeypatch.delenv("FCC_API_KEY", raising=False)
    monkeypatch.delenv("FCC_MODEL", raising=False)
    assert fcc_gateway.fcc_base_url() == "http://127.0.0.1:8082/v1"
    assert fcc_gateway.fcc_api_key() == "fcc-local"
    assert fcc_gateway.fcc_health_url() == "http://127.0.0.1:8082/health"
    assert fcc_gateway.fcc_model() == "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"


def test_fcc_health_check_success(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({"status": "healthy"}).encode()

    monkeypatch.setattr(fcc_gateway, "urlopen", lambda *_args, **_kwargs: Response())
    assert fcc_gateway.fcc_is_healthy(timeout=0.1)


def test_fcc_health_check_failure(monkeypatch):
    def fail(*_args, **_kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr(fcc_gateway, "urlopen", fail)
    assert not fcc_gateway.fcc_is_healthy(timeout=0.1)


def test_fcc_provider_is_opt_in(monkeypatch):
    monkeypatch.delenv("FCC_ENABLED", raising=False)
    monkeypatch.delenv("JENEFAR_PROVIDER_ORDER", raising=False)
    pool = ProviderPool()
    assert "fcc" not in pool.order()
    assert not pool.configured("fcc")


def test_fcc_provider_can_be_enabled_without_a_paid_key(monkeypatch):
    monkeypatch.setenv("FCC_ENABLED", "true")
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "fcc,openrouter")
    monkeypatch.delenv("FCC_API_KEY", raising=False)
    pool = ProviderPool()
    assert pool.order() == ["fcc", "openrouter"]
    assert pool.configured("fcc")
    assert pool.api_key("fcc") == "fcc-local"
    assert pool.model("fcc") == "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"


def test_llm_client_uses_fcc_base_url_and_token(monkeypatch):
    from types import SimpleNamespace

    from jenefar.core.llm import LLMClient

    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    import openai

    monkeypatch.setattr(openai, "OpenAI", fake_openai)
    monkeypatch.setenv("FCC_ENABLED", "true")
    monkeypatch.setenv("FCC_BASE_URL", "http://127.0.0.1:9191/v1")
    monkeypatch.setenv("FCC_API_KEY", "local-secret")
    client = LLMClient.__new__(LLMClient)
    client._clients = {}
    client.providers = ProviderPool()

    client._client("fcc")

    assert captured == {
        "api_key": "local-secret",
        "base_url": "http://127.0.0.1:9191/v1",
    }
