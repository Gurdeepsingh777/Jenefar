from jenefar.core.intent import ALLOWED_AGENTS, LLMIntentFallback
from jenefar.core.planner import Plan


def _plan(**kwargs) -> Plan:
    values = {
        "intent": "research",
        "agent": "research",
        "needs_tool": False,
        "confidence": 0.55,
        "reason": "fallback",
    }
    values.update(kwargs)
    return Plan(**values)


def test_high_confidence_skips_llm():
    calls = []

    def fake_llm(prompt: str) -> str:
        calls.append(prompt)
        return '{"intent": "coding", "agent": "python", "needs_tool": true, "reason": "x"}'

    original = _plan(confidence=0.9, agent="python", intent="coding")
    refined = LLMIntentFallback(llm_complete=fake_llm).refine("write a FastAPI endpoint", original)
    assert refined is original
    assert calls == []


def test_low_confidence_overrides_with_allowlisted_agent():
    original = _plan()

    def fake_llm(prompt: str) -> str:
        assert "json" in prompt.lower()
        return '{"intent": "local_development", "agent": "local_development", "needs_tool": true, "reason": "file edit"}'

    refined = LLMIntentFallback(llm_complete=fake_llm).refine("please change my script", original)
    assert refined is not original
    assert refined.agent == "local_development"
    assert refined.intent == "local_development"
    assert refined.needs_tool is True
    assert refined.confidence >= 0.75
    assert "file edit" in refined.reason


def test_unknown_agent_keeps_original_plan():
    original = _plan()

    def fake_llm(prompt: str) -> str:
        return '{"intent": "hacker", "agent": "shadow", "needs_tool": true, "reason": "nope"}'

    refined = LLMIntentFallback(llm_complete=fake_llm).refine("do something vague", original)
    assert refined is original


def test_bad_json_keeps_original_plan():
    original = _plan()
    refined = LLMIntentFallback(llm_complete=lambda prompt: "not-json").refine("vague", original)
    assert refined is original


def test_timeout_keeps_original_plan():
    original = _plan()

    def fake_llm(prompt: str) -> str:
        raise TimeoutError("offline")

    refined = LLMIntentFallback(llm_complete=fake_llm).refine("vague", original)
    assert refined is original


def test_allowed_agents_cover_router_specialists():
    expected = {
        "repository",
        "local_development",
        "gui_vision",
        "automation",
        "kali",
        "python",
        "cybersecurity",
        "bugbounty",
        "robotics",
        "utility",
        "research",
    }
    assert expected <= set(ALLOWED_AGENTS)
