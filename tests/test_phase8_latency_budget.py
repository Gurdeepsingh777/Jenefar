import time

from jenefar.agents.llm_agent import BaseLLMAgent
from jenefar.core.agent import AgentContext, AgentResult
from jenefar.core.llm import LLMClient, LLMResponse
from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.offline.local_llm import LocalLLMClient


def test_execution_budget_defaults_to_180_seconds(monkeypatch):
    # The project .env is loaded when the suite imports Jenefar; isolate this
    # default-value test from a developer's runtime timeout preferences.
    monkeypatch.delenv("JENEFAR_AGENT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("JENEFAR_AGENT_TIMEOUT_RESEARCH", raising=False)
    assert JenefarOrchestrator._execution_budget_seconds("research", "research") == 180.0


def test_execution_budget_is_clamped_and_agent_override_wins(monkeypatch):
    monkeypatch.setenv("JENEFAR_AGENT_TIMEOUT_SECONDS", "25")
    monkeypatch.setenv("JENEFAR_AGENT_TIMEOUT_RESEARCH", "500")
    assert JenefarOrchestrator._execution_budget_seconds("research", "research") == 300.0
    monkeypatch.setenv("JENEFAR_AGENT_TIMEOUT_RESEARCH", "12")
    assert JenefarOrchestrator._execution_budget_seconds("research", "research") == 12.0


def test_remaining_timeout_rejects_expired_deadline():
    try:
        LLMClient._remaining_timeout(time.monotonic() - 1)
    except TimeoutError as exc:
        assert "execution budget exhausted" in str(exc)
    else:
        raise AssertionError("expired deadline was not rejected")


def test_remaining_timeout_returns_remaining_budget():
    deadline = time.monotonic() + 3
    remaining = LLMClient._remaining_timeout(deadline)
    assert 2.0 < remaining <= 3.0


def test_llm_agent_propagates_deadline():
    captured = {}

    class FakeLLM:
        def complete(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return LLMResponse("ok", provider="test")

    agent = object.__new__(BaseLLMAgent)
    agent.system_prompt = "test"
    agent.use_web_search = False
    agent.use_tools = False
    agent.allow_action_tools = False
    agent.max_tool_rounds = 1
    agent.model_role = "fast"
    agent.llm = FakeLLM()
    agent.tool_broker = None

    deadline = time.monotonic() + 10
    result = agent.run(AgentContext(
        task="hello",
        metadata={
            "response_language": "Hinglish",
            "deadline_monotonic": deadline,
        },
    ))

    assert result.content == "ok"
    assert captured["deadline"] == deadline


def test_local_llm_budget_is_bounded_by_remaining_deadline(monkeypatch):
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_TIMEOUT_SECONDS", "45")
    client = LocalLLMClient()
    assert client.timeout_seconds == 45.0
    assert client.timeout_seconds >= 5.0



def test_unpinned_local_model_selection_prefers_smaller_installed_model(monkeypatch):
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL", raising=False)
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL_FAST", raising=False)
    client = LocalLLMClient()
    selected = client._select_installed_model(
        ["qwen3.8:27b", "qwen3:8b", "qwen3:1.7b"],
        "Ollama",
    )
    assert selected == "qwen3:1.7b"


def test_explicit_large_local_model_requires_opt_in(monkeypatch):
    import psutil
    from types import SimpleNamespace

    monkeypatch.setenv("JENEFAR_LOCAL_LLM_MODEL", "qwen3.8:27b")
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL_FAST", raising=False)
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_ALLOW_LARGE_MODEL", raising=False)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=64 * 1024**3))
    client = LocalLLMClient()
    assert client._select_installed_model(
        ["qwen3:8b", "qwen3.8:27b"],
        "Ollama",
    ) == "qwen3:8b"

    monkeypatch.setenv("JENEFAR_LOCAL_LLM_ALLOW_LARGE_MODEL", "1")
    assert client._select_installed_model(
        ["qwen3:8b", "qwen3.8:27b"],
        "Ollama",
    ) == "qwen3.8:27b"


def test_explicit_oversized_model_is_overridden_under_memory_pressure(monkeypatch):
    import psutil
    from types import SimpleNamespace

    monkeypatch.setenv("JENEFAR_LOCAL_LLM_MODEL", "qwen3.8:27b")
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_MODEL_FAST", raising=False)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=2 * 1024**3))
    client = LocalLLMClient()
    selected = client._select_installed_model(
        ["qwen3.8:27b", "qwen3:8b", "qwen3:1.7b"],
        "Ollama",
    )
    assert selected == "qwen3:1.7b"

def test_expired_deadline_preserves_explicit_offline_fallback_reply():
    from types import SimpleNamespace

    expired = 100.0
    offline_result = SimpleNamespace(metadata={"provider": "offline_unavailable"})
    online_result = SimpleNamespace(metadata={"provider": "openai"})

    assert not JenefarOrchestrator._late_dispatch_result_should_fail(
        expired, offline_result, now=101.0
    )
    assert JenefarOrchestrator._late_dispatch_result_should_fail(
        expired, online_result, now=101.0
    )
    assert not JenefarOrchestrator._late_dispatch_result_should_fail(
        102.0, online_result, now=101.0
    )

def test_online_llm_window_reserves_time_for_local_fallback(monkeypatch):
    monkeypatch.setenv("JENEFAR_ONLINE_LLM_BUDGET_SECONDS", "20")
    monkeypatch.setenv("JENEFAR_LOCAL_FALLBACK_RESERVE_SECONDS", "45")
    now = 100.0
    deadline = 280.0
    assert LLMClient._online_request_deadline(deadline, now=now) == 120.0


def test_short_task_budget_skips_online_window_and_reserves_local_time(monkeypatch):
    monkeypatch.setenv("JENEFAR_ONLINE_LLM_BUDGET_SECONDS", "20")
    monkeypatch.setenv("JENEFAR_LOCAL_FALLBACK_RESERVE_SECONDS", "45")
    now = 100.0
    deadline = 130.0
    assert LLMClient._online_request_deadline(deadline, now=now) == 100.0


def test_online_window_is_limited_by_local_fallback_reserve(monkeypatch):
    monkeypatch.setenv("JENEFAR_ONLINE_LLM_BUDGET_SECONDS", "60")
    monkeypatch.setenv("JENEFAR_LOCAL_FALLBACK_RESERVE_SECONDS", "45")
    now = 100.0
    deadline = 160.0
    assert LLMClient._online_request_deadline(deadline, now=now) == 115.0
