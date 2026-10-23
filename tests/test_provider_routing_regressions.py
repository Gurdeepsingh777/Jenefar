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
    assert ProviderPool().order() == ["groq", "gemini", "openrouter", "apinex", "unorouter", "apmix", "nvidia", "kilo", "qwen", "openai"]


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


def test_additional_openai_compatible_provider_configuration(monkeypatch):
    from jenefar.core.provider_pool import ProviderPool

    expected = {
        "unorouter": ("UNOROUTER_API_KEY", "https://api.unorouter.com/v1"),
        "apmix": ("APMIX_API_KEY", "https://api.apmix.ai/v1"),
        "nvidia": ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
        "kilo": ("KILO_API_KEY", "https://ai-gateway.kilo.ai/api/v1"),
        "qwen": ("DASHSCOPE_API_KEY", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    }
    pool = ProviderPool()
    for name, (key_env, base_url) in expected.items():
        monkeypatch.setenv(key_env, "test-key")
        assert pool.configured(name)
        assert pool.status()[name]["base_url"] == base_url
        monkeypatch.delenv(key_env, raising=False)


def test_qwen_base_url_can_be_set_for_region_or_workspace(monkeypatch):
    pool = ProviderPool()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")
    assert pool.status()["qwen"]["base_url"] == "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
