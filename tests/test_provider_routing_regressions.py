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


def test_chat_tool_loop_preserves_gemini_thought_signature(monkeypatch):
    from types import SimpleNamespace

    from jenefar.core.llm import LLMClient

    captured = []

    class FakeBroker:
        def schemas(self, **_kwargs):
            return [{
                "type": "function",
                "name": "scope_check",
                "description": "Check scope.",
                "parameters": {"type": "object", "properties": {}},
            }]

        def invoke(self, name, arguments):
            return '{"status": "ok", "result": {"allowed": true}}'

    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            captured.append(kwargs["messages"])
            if self.calls == 1:
                function = SimpleNamespace(
                    name="scope_check",
                    arguments='{"target": "192.168.29.0/24"}',
                )
                call = SimpleNamespace(
                    id="call_1",
                    type="function",
                    function=function,
                    extra_content={"google": {"thought_signature": "sig-abc"}},
                )
                message = SimpleNamespace(
                    content=None,
                    tool_calls=[call],
                    role="assistant",
                )
                message.model_dump = lambda exclude_none=True: {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "scope_check",
                            "arguments": '{"target": "192.168.29.0/24"}',
                        },
                        "extra_content": {"google": {"thought_signature": "sig-abc"}},
                    }],
                }
                choice = SimpleNamespace(message=message)
                return SimpleNamespace(choices=[choice], id="resp-1")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="scan ready", tool_calls=None))],
                id="resp-2",
            )

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    client = LLMClient.__new__(LLMClient)
    client._clients = {"gemini": FakeClient()}
    monkeypatch.setattr(LLMClient, "_client", lambda self, provider: self._clients[provider])

    result = LLMClient._complete_chat(
        client,
        "gemini",
        "scan my network",
        instructions="test",
        tool_broker=FakeBroker(),
        allow_action_tools=True,
        max_tool_rounds=4,
        model="gemini-test",
        model_role="reasoning",
    )
    assert result.text == "scan ready"
    followup = captured[1]
    assistant = next(item for item in followup if item.get("role") == "assistant")
    assert assistant["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "sig-abc"
