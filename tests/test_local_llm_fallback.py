from __future__ import annotations

import json

from jenefar.offline.local_llm import LocalLLMClient, LocalModelInfo


def test_auto_detect_uses_native_ollama_api_and_installed_model(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_API", "auto")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_MODEL", "gemini-4-argon")
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL_FAST", raising=False)

    def fake_get(url, *, timeout=3.0):
        assert timeout > 0
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen3:8b"}, {"name": "llama3.2:latest"}]}
        raise AssertionError(f"Unexpected model discovery URL: {url}")

    monkeypatch.setattr(LocalLLMClient, "_get_json", staticmethod(fake_get))
    client = LocalLLMClient()
    info = client.detect()

    assert info == LocalModelInfo("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    assert client.model == "qwen3:8b"


def test_auto_detect_keeps_openai_compatible_local_servers(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_API", "auto")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL", raising=False)
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL_FAST", raising=False)

    def fake_get(url, *, timeout=3.0):
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-instruct-model"}]}
        raise AssertionError(f"Unexpected model discovery URL: {url}")

    monkeypatch.setattr(LocalLLMClient, "_get_json", staticmethod(fake_get))
    info = LocalLLMClient().detect()

    assert info == LocalModelInfo("http://127.0.0.1:1234/v1", "local-instruct-model", "openai")


def test_native_ollama_tool_call_round_trip_uses_same_local_broker(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_API", "auto")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL", raising=False)
    client = LocalLLMClient()
    monkeypatch.setattr(
        client,
        "detect",
        lambda model_role=None: LocalModelInfo("http://127.0.0.1:11434", "qwen3:8b", "ollama"),
    )

    calls = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {"name": "memory_recall", "arguments": {"query": "voice setup"}}
                }],
            }
        },
        {"message": {"role": "assistant", "content": "Maine local memory check kar li hai."}},
    ]
    requests = []

    def fake_request(url, payload, *, timeout):
        requests.append((url, payload, timeout))
        return calls.pop(0)

    monkeypatch.setattr(client, "_request_json", fake_request)

    class Broker:
        def __init__(self):
            self.invocations = []

        def invoke(self, name, arguments):
            self.invocations.append((name, arguments))
            return json.dumps({"status": "ok", "result": [{"content": "local note"}]})

    broker = Broker()
    answer, pending = client.complete(
        prompt="Voice setup ki purani notes check karo.",
        instructions="Use the provided Jenefar tools when helpful.",
        tools=[{
            "type": "function",
            "name": "memory_recall",
            "description": "Search local memory",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }],
        tool_broker=broker,
        max_tool_rounds=3,
    )

    assert answer == "Maine local memory check kar li hai."
    assert pending == []
    assert broker.invocations == [("memory_recall", {"query": "voice setup"})]
    assert requests[0][0] == "http://127.0.0.1:11434/api/chat"
    assert requests[0][2] == 240
    history = requests[1][1]["messages"]
    assert history[-2]["role"] == "assistant"
    assert history[-2]["tool_calls"][0]["function"]["name"] == "memory_recall"
    assert history[-1]["role"] == "tool"
    assert history[-1]["tool_name"] == "memory_recall"
    assert history[-1]["content"].find("local note") >= 0


def test_tool_arguments_accept_openai_strings_and_ollama_objects():
    assert LocalLLMClient._tool_arguments('{"path":"/tmp/demo"}') == {"path": "/tmp/demo"}
    assert LocalLLMClient._tool_arguments({"path": "/tmp/demo"}) == {"path": "/tmp/demo"}
    assert LocalLLMClient._tool_arguments("not-json") == {}


def test_offline_fallback_is_used_after_all_online_providers_fail(monkeypatch):
    from jenefar.core.llm import LLMClient, LLMResponse

    monkeypatch.setattr("jenefar.core.llm.internet_available", lambda: True)
    client = LLMClient()
    monkeypatch.setattr(client.providers, "order", lambda: ["gemini"])
    monkeypatch.setattr(client.providers, "available", lambda _provider: True)
    monkeypatch.setattr(client.providers, "model", lambda _provider, _role: "online-model")

    def fail_online(*_args, **_kwargs):
        raise RuntimeError("insufficient_quota: credits exhausted")

    local_calls = []

    def local_fallback(*args, **kwargs):
        local_calls.append((args, kwargs))
        return LLMResponse(
            "Offline local answer.",
            "local",
            model="qwen3:8b",
            model_role="fast",
        )

    monkeypatch.setattr(client, "_complete_online", fail_online)
    monkeypatch.setattr(client, "_complete_local", local_fallback)

    result = client.complete("Explain the local project", model_role="fast")

    assert result.provider == "local"
    assert result.text == "Offline local answer."
    assert len(local_calls) == 1
