from __future__ import annotations

import httpx

from jenefar.core.model_catalog import list_provider_models
from jenefar.core.provider_pool import ProviderPool


def test_gemini_catalog_returns_only_compatible_chat_models(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")

    class Response:
        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {
                "models": [
                    {
                        "name": "models/gemini-3.8-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.1-pro-preview",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.8-flash-tts",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/text-embedding-004",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            }

    captured = {}

    def fake_get(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(httpx, "get", fake_get)
    result = list_provider_models("gemini", ProviderPool())

    assert result["source"] == "provider-api"
    assert result["provider"] == "gemini"
    assert "gemini-3.8-flash" in result["models"]
    assert "gemini-3.1-pro-preview" in result["models"]
    assert "gemini-3.8-flash-tts" not in result["models"]
    assert "text-embedding-004" not in result["models"]
    assert captured["url"].endswith("/v1beta/models")
    assert captured["headers"]["x-goog-api-key"] == "test-gemini-key"


def test_gemini_catalog_has_clear_fallback_when_api_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")

    def fail_get(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", fail_get)
    result = list_provider_models("gemini", ProviderPool())

    assert result["source"] == "fallback"
    assert "gemini-3.8-flash" in result["models"]
    assert "diagnostic" in result
