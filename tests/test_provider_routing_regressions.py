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
    assert ProviderPool().order() == ["openai", "openrouter", "gemini", "groq"]


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


def test_default_provider_order_prefers_groq_over_openrouter(monkeypatch):
    monkeypatch.delenv("JENEFAR_PROVIDER_ORDER", raising=False)
    assert ProviderPool().order() == ["openai", "groq", "gemini", "openrouter"]
