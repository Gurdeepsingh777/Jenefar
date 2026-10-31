from __future__ import annotations

import time

from jenefar.core.llm import LLMClient


class _FailingProviderPool:
    def order_for_role(self, _role: str) -> list[str]:
        return ["oxion"]

    def available(self, _name: str) -> bool:
        return True

    def model(self, _name: str, _role: str) -> str:
        return "test-model"

    def record_latency(self, *_args, **_kwargs) -> None:
        return None

    def reset(self, _name: str) -> None:
        return None


def test_online_only_failure_returns_response_without_constructor_typeerror(monkeypatch):
    monkeypatch.setenv("JENEFAR_DISABLE_LOCAL_FALLBACK", "1")
    monkeypatch.setattr("jenefar.core.llm.internet_available", lambda: True)

    client = LLMClient.__new__(LLMClient)
    client.explicit_model = None
    client.default_role = "fast"
    client.providers = _FailingProviderPool()
    client.selected_model = lambda _role=None: ("test-model", "fast")

    def fail_provider(*_args, **_kwargs):
        raise RuntimeError("provider maintenance")

    client._complete_online = fail_provider

    response = client.complete(
        "test request",
        deadline=time.monotonic() + 30,
    )

    assert response.provider == "online_unavailable"
    assert "Local fallback is disabled" in response.text
    assert "provider maintenance" in response.text
