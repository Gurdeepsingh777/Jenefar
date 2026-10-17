from __future__ import annotations

from jenefar.core.llm import LLMClient, LLMResponse
from jenefar.core.model_router import ModelRouter
from jenefar.offline.local_llm import LocalLLMClient, LocalModelInfo


def test_local_model_is_used_after_online_quotas_are_exhausted(monkeypatch):
    ModelRouter.clear_runtime_override()
    client = LLMClient()
    attempted: list[str] = []

    monkeypatch.setattr("jenefar.core.llm.internet_available", lambda: True)
    monkeypatch.setattr(client.providers, "order", lambda: ["openai", "gemini"])
    monkeypatch.setattr(client.providers, "available", lambda _name: True)
    monkeypatch.setattr(
        client.providers, "model", lambda name, _role="fast": f"{name}-test-model"
    )

    def fail_online(provider, *_args, **_kwargs):
        attempted.append(provider)
        if provider == "openai":
            raise RuntimeError("credit_balance_exhausted: insufficient_quota")
        raise RuntimeError("RESOURCE_EXHAUSTED: quota exceeded")

    monkeypatch.setattr(client, "_complete_online", fail_online)
    monkeypatch.setattr(
        client,
        "_complete_local",
        lambda _prompt, **kwargs: LLMResponse(
            "Local model response",
            "local",
            model="llama3.2:latest",
            model_role=kwargs["model_role"],
        ),
    )

    response = client.complete("Explain this in Hindi.")

    assert attempted == ["openai", "gemini"]
    assert response.provider == "local"
    assert response.model == "llama3.2:latest"
    assert response.text == "Local model response"


def test_local_only_installation_counts_as_available(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client.providers, "configured", lambda _name: False)
    monkeypatch.setattr(client.local, "detect", lambda model_role=None: object())

    assert client.available() is True


def test_explicit_ollama_preference_can_fall_back_to_openai_compatible_route(monkeypatch):
    client = LocalLLMClient()
    client.api = "ollama"
    info = LocalModelInfo("http://127.0.0.1:11434", "llama3.2:latest", "ollama")
    calls: list[str] = []

    def fake_request(url, _payload, *, timeout):
        calls.append(url)
        if url.endswith("/api/chat"):
            raise RuntimeError("HTTP Error 404: Not Found")
        return {"choices": [{"message": {"content": "Recovered local response"}}]}

    monkeypatch.setattr(client, "_request_json", fake_request)

    result, updated_info = client._request_chat_with_fallback(
        info,
        {"model": info.model, "messages": [{"role": "user", "content": "hello"}]},
        timeout=5,
    )

    assert calls == [
        "http://127.0.0.1:11434/api/chat",
        "http://127.0.0.1:11434/v1/chat/completions",
    ]
    assert result["choices"][0]["message"]["content"] == "Recovered local response"
    assert updated_info.api == "openai"
    assert updated_info.base_url == "http://127.0.0.1:11434/v1"


def test_openai_compatible_404_falls_back_to_ollama_and_strips_tool_choice(monkeypatch):
    client = LocalLLMClient()
    client.api = "openai"
    info = LocalModelInfo("http://127.0.0.1:11434/v1", "llama3.2:latest", "openai")
    calls: list[tuple[str, dict]] = []

    def fake_request(url, payload, *, timeout):
        calls.append((url, dict(payload)))
        if url.endswith("/chat/completions"):
            raise RuntimeError("HTTP Error 404: Not Found")
        return {"message": {"content": "Recovered through Ollama"}}

    monkeypatch.setattr(client, "_request_json", fake_request)

    result, updated_info = client._request_chat_with_fallback(
        info,
        {
            "model": info.model,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"type": "function", "function": {"name": "test"}}],
            "tool_choice": "auto",
        },
        timeout=5,
    )

    assert calls[0][0] == "http://127.0.0.1:11434/v1/chat/completions"
    assert calls[1][0] == "http://127.0.0.1:11434/api/chat"
    assert "tool_choice" not in calls[1][1]
    assert result["message"]["content"] == "Recovered through Ollama"
    assert updated_info.api == "ollama"
    assert updated_info.base_url == "http://127.0.0.1:11434"


def test_openai_responses_empty_text_raises_for_provider_failover(monkeypatch):
    from types import SimpleNamespace

    from jenefar.core.llm import LLMClient

    client = LLMClient()

    class Responses:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(output=[], output_text="", id="empty-response")

    monkeypatch.setattr(client, "_client", lambda _provider: SimpleNamespace(responses=Responses()))

    import pytest
    with pytest.raises(RuntimeError, match="returned an empty text response"):
        client._complete_openai_responses(
            "openai",
            "Please answer",
            instructions="Be helpful.",
            use_web_search=False,
            tool_broker=None,
            allow_action_tools=False,
            max_tool_rounds=1,
            model="test-model",
            model_role="fast",
        )


def test_openai_compatible_chat_empty_text_raises_for_provider_failover(monkeypatch):
    from types import SimpleNamespace

    import pytest

    from jenefar.core.llm import LLMClient

    client = LLMClient()
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=[]),
            )
        ]
    )

    class Completions:
        @staticmethod
        def create(**_kwargs):
            return response

    chat = SimpleNamespace(completions=Completions())
    monkeypatch.setattr(client, "_client", lambda _provider: SimpleNamespace(chat=chat))

    with pytest.raises(RuntimeError, match="returned an empty chat response"):
        client._complete_chat(
            "gemini",
            "Please answer",
            instructions="Be helpful.",
            tool_broker=None,
            allow_action_tools=False,
            max_tool_rounds=1,
            model="test-model",
            model_role="fast",
        )


def test_local_fallback_skips_tool_catalog_for_plain_questions():
    tools = [
        {"type": "function", "name": "rea_status", "description": "Check REA MCP."},
        {"type": "function", "name": "memory_recall", "description": "Search stored notes."},
        {"type": "function", "name": "workspace_read_file", "description": "Read a project file."},
    ]

    selected = LLMClient._select_local_tools("Explain Python loops in Hinglish.", tools)

    assert selected == []


def test_local_fallback_keeps_only_rea_tools_for_rea_requests():
    tools = [
        {"type": "function", "name": "rea_status", "description": "Check REA MCP status."},
        {"type": "function", "name": "rea_list_tools", "description": "List REA server tools."},
        {"type": "function", "name": "rea_call", "description": "Call a listed REA tool."},
        {"type": "function", "name": "workspace_read_file", "description": "Read a project file."},
    ]

    selected = LLMClient._select_local_tools("Connect REA MCP and list tools.", tools)

    assert [tool["name"] for tool in selected] == ["rea_status", "rea_list_tools", "rea_call"]


def test_local_fallback_filters_repo_tools_and_supports_legacy_all_mode(monkeypatch):
    tools = [
        {"type": "function", "name": "workspace_read_file", "description": "Read files."},
        {"type": "function", "name": "repository_analyze", "description": "Analyze a repository."},
        {"type": "function", "name": "rea_status", "description": "Check REA MCP status."},
    ]

    selected = LLMClient._select_local_tools("Inspect the repository files and fix the code.", tools)

    assert [tool["name"] for tool in selected] == ["workspace_read_file", "repository_analyze"]
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_TOOL_MODE", "all")
    assert LLMClient._select_local_tools("Explain Python.", tools) == tools
