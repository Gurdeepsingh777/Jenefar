from __future__ import annotations

from jenefar.core.provider_pool import ProviderPool


def test_openrouter_key_is_not_treated_as_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    pool = ProviderPool()
    assert not pool.configured("openai")
    assert pool.configured("openrouter")


def test_current_default_provider_order(monkeypatch):
    monkeypatch.delenv("JENEFAR_PROVIDER_ORDER", raising=False)
    assert ProviderPool().order() == ["oxion", "openai", "openrouter", "gemini", "groq", "cerebras"]


def test_groq_default_model_is_current():
    assert ProviderPool().model("groq") == "openai/gpt-oss-120b"


class FakeBroker:
    def schemas(self, **_kwargs):
        return [{
            "type": "function",
            "name": "hello",
            "description": "Say hello.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            "strict": True,
        }]


def test_chat_tool_schema_conversion():
    from jenefar.core.llm import LLMClient

    tools = LLMClient._chat_tools(FakeBroker(), False)
    assert tools == [{
        "type": "function",
        "function": {
            "name": "hello",
            "description": "Say hello.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    }]


def test_explicit_provider_order_can_prefer_groq_over_openrouter(monkeypatch):
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openai,groq,gemini,openrouter")
    assert ProviderPool().order() == ["openai", "groq", "gemini", "openrouter"]


def test_adaptive_routing_penalty_clears_after_provider_recovers(monkeypatch):
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openai,groq")
    monkeypatch.setenv("JENEFAR_ADAPTIVE_ROUTING", "1")
    monkeypatch.setenv("JENEFAR_ROUTING_WARMUP_SAMPLES", "2")
    pool = ProviderPool()

    for _ in range(2):
        pool.record_latency("openai", 0.05, success=True)
        pool.record_latency("groq", 0.07, success=True)
    assert pool.order_for_role() == ["openai", "groq"]

    for _ in range(4):
        pool.record_latency("openai", 0.05, success=False)
    assert pool.order_for_role() == ["groq", "openai"]

    # The diagnostic lifetime count is preserved, but successful recovery
    # clears the adaptive failure streak and restores latency-based ordering.
    for _ in range(4):
        pool.record_latency("openai", 0.05, success=True)
    assert pool.failure_samples["openai"] == 4
    assert pool.failure_streaks["openai"] == 0
    assert pool.order_for_role() == ["openai", "groq"]
