import time

from jenefar.agents.llm_agent import BaseLLMAgent
from jenefar.core.agent import AgentContext, AgentResult
from jenefar.core.llm import LLMClient, LLMResponse
from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.offline.local_llm import LocalLLMClient


def test_execution_budget_defaults_to_60_seconds():
    assert JenefarOrchestrator._execution_budget_seconds("research", "research") == 60.0


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
        def complete(self, **kwargs):
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
