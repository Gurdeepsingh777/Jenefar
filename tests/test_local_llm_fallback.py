from __future__ import annotations

import json

from jenefar.offline.local_llm import LocalLLMClient, LocalModelInfo


def test_auto_detect_uses_native_ollama_api_and_installed_model(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_API", "auto")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    # This test validates request formatting, not the user's opt-in thinking mode.
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_THINK", "false")
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
    from types import SimpleNamespace
    import psutil

    # Make the RAM-pressure configuration deterministic across CI and local hosts.
    # Existing user .env settings may still specify the old 10m/4096/384 defaults.
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_API", "auto")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_KEEP_ALIVE", "10m")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_NUM_CTX", "4096")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_NUM_PREDICT", "384")
    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: SimpleNamespace(available=2 * 1024**3),
    )
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
    assert requests[0][2] == 45.0
    assert requests[0][1]["think"] is False
    assert requests[0][1]["keep_alive"] == "30s"
    assert requests[0][1]["options"]["num_ctx"] == 2048
    assert requests[0][1]["options"]["num_predict"] == 192
    history = requests[1][1]["messages"]
    assert history[-2]["role"] == "assistant"
    assert history[-2]["tool_calls"][0]["function"]["name"] == "memory_recall"
    assert history[-1]["role"] == "tool"
    assert history[-1]["tool_name"] == "memory_recall"
    assert history[-1]["content"].find("local note") >= 0


def test_auto_mode_retries_alternate_chat_protocol_after_route_404(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_API", "auto")
    client = LocalLLMClient()
    from jenefar.offline.local_llm import LocalModelInfo

    monkeypatch.setattr(
        client,
        "detect",
        lambda model_role=None: LocalModelInfo(
            "http://127.0.0.1:11434/v1", "qwen3:8b", "openai"
        ),
    )
    requests = []

    def fake_request(url, payload, *, timeout):
        requests.append(url)
        if url.endswith("/v1/chat/completions"):
            raise RuntimeError(
                f"HTTP 404 from local LLM endpoint {url}: 404 page not found"
            )
        assert url == "http://127.0.0.1:11434/api/chat"
        return {"message": {"role": "assistant", "content": "Offline answer works."}}

    monkeypatch.setattr(client, "_request_json", fake_request)
    answer, pending = client.complete(
        prompt="Reply offline",
        instructions="You are Jenefar.",
    )

    assert answer == "Offline answer works."
    assert pending == []
    assert requests == [
        "http://127.0.0.1:11434/v1/chat/completions",
        "http://127.0.0.1:11434/api/chat",
    ]


def test_local_route_404_detection_does_not_treat_missing_model_as_route_error():
    assert LocalLLMClient._is_chat_route_not_found(
        RuntimeError("HTTP 404 from local LLM endpoint: 404 page not found")
    )
    assert not LocalLLMClient._is_chat_route_not_found(
        RuntimeError("HTTP 404 from local LLM endpoint: model 'qwen3:8b' not found")
    )


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


def test_model_parameter_size_parser_understands_model_tags_and_ollama_details():
    assert LocalLLMClient._model_parameter_billions("qwen3.8:27b") == 27.0
    assert LocalLLMClient._model_parameter_billions(
        "custom-model", {"parameter_size": "8.0B"}
    ) == 8.0


def test_local_timeout_switches_promptly_to_smaller_installed_model(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_PRIMARY_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_RETRY_TIMEOUT_SECONDS", "180")
    client = LocalLLMClient()
    large = LocalModelInfo("http://127.0.0.1:11434", "qwen3.8:27b", "ollama")
    smaller = LocalModelInfo("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    monkeypatch.setattr(client, "detect", lambda model_role=None: large)
    monkeypatch.setattr(client, "_find_smaller_ollama_model", lambda _info: smaller)

    attempts = []

    def fake_request(info, payload, *, timeout):
        attempts.append((info.model, dict(payload), timeout))
        if len(attempts) == 1:
            raise RuntimeError("Could not reach local LLM endpoint: timed out")
        return {"message": {"role": "assistant", "content": "Recovered with Qwen 8B"}}, info

    monkeypatch.setattr(client, "_request_chat_with_fallback", fake_request)
    answer, pending = client.complete(
        prompt="Reply exactly with a short confirmation.",
        instructions="You are Jenefar. Be concise.",
    )

    assert answer == "Recovered with Qwen 8B"
    assert pending == []
    assert [item[0] for item in attempts] == ["qwen3.8:27b", "qwen3:8b"]
    assert attempts[0][2] == 30.0
    assert attempts[1][2] == 180
    assert attempts[1][1]["options"]["num_ctx"] == 2048
    assert attempts[1][1]["options"]["num_predict"] == 192
    assert attempts[1][1]["think"] is False
    assert attempts[1][1]["model"] == "qwen3:8b"
    assert client.model == "qwen3:8b"


def test_compact_retry_preserves_tools_for_action_requests():
    client = LocalLLMClient()
    info = LocalModelInfo("http://127.0.0.1:11434", "qwen3.8:27b", "ollama")
    tools = [{
        "type": "function",
        "function": {
            "name": "scope_check",
            "description": "Check the configured authorized scope.",
            "parameters": {"type": "object", "properties": {}},
        },
    }]
    payload = {
        "model": info.model,
        "messages": [
            {"role": "system", "content": "Follow authorization policy."},
            {"role": "user", "content": "Check my authorized scope."},
        ],
        "tools": tools,
        "think": True,
        "options": {"num_ctx": 4096, "num_predict": 384},
    }

    compact = client._compact_retry_payload(payload, info)

    assert compact["tools"] == tools
    assert compact["options"]["num_ctx"] == 2048
    assert compact["options"]["num_predict"] == 192
    assert compact["think"] is False
    assert payload["options"]["num_ctx"] == 4096
    assert payload["think"] is True


def test_timeout_fallback_model_is_preferred_on_later_detection():
    client = LocalLLMClient()
    client._runtime_fallback_model = "qwen3:8b"

    assert client._select_installed_model(
        ["qwen3.8:27b", "qwen3:8b"], "Ollama"
    ) == "qwen3:8b"



def test_smaller_model_selection_prefers_largest_installed_model_below_current(monkeypatch):
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_FALLBACK_MODEL", raising=False)
    monkeypatch.setattr(
        LocalLLMClient,
        "_get_json",
        staticmethod(lambda *_args, **_kwargs: {
            "models": [
                {"name": "qwen3:1b", "details": {"parameter_size": "1.0B"}},
                {"name": "qwen3:8b", "details": {"parameter_size": "8.0B"}},
                {"name": "qwen3.8:27b", "details": {"parameter_size": "27B"}},
            ]
        }),
    )
    client = LocalLLMClient()
    current = LocalModelInfo("http://127.0.0.1:11434", "qwen3.8:27b", "ollama")

    selected = client._find_smaller_ollama_model(current)

    assert selected == LocalModelInfo("http://127.0.0.1:11434", "qwen3:8b", "ollama")

def test_ollama_options_clamp_legacy_env_defaults_under_ram_pressure(monkeypatch):
    from types import SimpleNamespace
    import psutil
    from jenefar.offline.local_llm import LocalLLMClient

    monkeypatch.setenv("JENEFAR_LOCAL_LLM_KEEP_ALIVE", "10m")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_NUM_CTX", "4096")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_NUM_PREDICT", "384")
    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: SimpleNamespace(available=2 * 1024**3),
    )

    options = LocalLLMClient._ollama_request_options()
    assert options["keep_alive"] == "30s"
    assert options["options"]["num_ctx"] == 2048
    assert options["options"]["num_predict"] == 192

def test_local_timeout_defaults_allow_slower_cpu_models(monkeypatch):
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_PRIMARY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_RETRY_TIMEOUT_SECONDS", raising=False)
    client = LocalLLMClient()
    info = LocalModelInfo("http://127.0.0.1:8080", "custom-model", "openai")
    timeouts = []

    def fake_request(_url, _payload, *, timeout):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            raise RuntimeError("Could not reach local LLM endpoint: timed out")
        return {"choices": [{"message": {"role": "assistant", "content": "Recovered"}}]}

    monkeypatch.setattr(client, "detect", lambda model_role=None: info)
    monkeypatch.setattr(client, "_request_json", fake_request)
    answer, pending = client.complete(
        prompt="Reply briefly.",
        instructions="Be concise.",
    )
    assert answer == "Recovered"
    assert pending == []
    assert timeouts == [45.0, 120.0]


def test_timeout_failure_recommends_a_model_smaller_than_qwen_8b():
    assert LocalLLMClient._recommended_smaller_model_tag("qwen3:8b") == "qwen3:4b"
    assert LocalLLMClient._recommended_smaller_model_tag("qwen3:4b") == "qwen3:1.7b"
    assert LocalLLMClient._recommended_smaller_model_tag("qwen3:1.7b") == "qwen3:0.6b"

def test_local_timeout_walks_down_multiple_installed_models(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_PRIMARY_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_RETRY_TIMEOUT_SECONDS", "40")
    client = LocalLLMClient()
    client.timeout_seconds = 100.0
    model27 = LocalModelInfo("http://127.0.0.1:11434", "qwen3.8:27b", "ollama")
    model8 = LocalModelInfo("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    model4 = LocalModelInfo("http://127.0.0.1:11434", "qwen3:4b", "ollama")
    monkeypatch.setattr(client, "detect", lambda model_role=None: model27)
    monkeypatch.setattr(client, "_unload_ollama_model", lambda *args, **kwargs: True)

    def find_next(info):
        return {
            "qwen3.8:27b": model8,
            "qwen3:8b": model4,
        }.get(info.model)

    monkeypatch.setattr(client, "_find_smaller_ollama_model", find_next)
    attempts = []

    def fake_request(info, payload, *, timeout):
        attempts.append((info.model, timeout))
        if info.model in {"qwen3.8:27b", "qwen3:8b"}:
            raise RuntimeError("Could not reach local LLM endpoint: timed out")
        return {"message": {"role": "assistant", "content": "Recovered with Qwen 4B"}}, info

    monkeypatch.setattr(client, "_request_chat_with_fallback", fake_request)
    answer, pending = client.complete(
        prompt="Answer briefly.",
        instructions="Be concise.",
    )
    assert answer == "Recovered with Qwen 4B"
    assert pending == []
    assert [model for model, _timeout in attempts] == [
        "qwen3.8:27b", "qwen3:8b", "qwen3:4b"
    ]
