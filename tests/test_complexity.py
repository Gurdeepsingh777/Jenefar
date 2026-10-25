from types import SimpleNamespace

from jenefar.core.complexity import ComplexityClassifier, tool_round_budget


def test_short_greeting_is_simple():
    result = ComplexityClassifier().classify("hi")
    assert result.level == "simple"


def test_time_query_is_simple():
    plan = SimpleNamespace(agent="utility", needs_tool=True, is_compound=False, confidence=0.98)
    result = ComplexityClassifier().classify("what time is it", plan)
    assert result.level == "simple"


def test_single_file_edit_is_standard():
    plan = SimpleNamespace(
        agent="local_development",
        needs_tool=True,
        is_compound=False,
        confidence=0.96,
    )
    result = ComplexityClassifier().classify("edit example.py and add a docstring", plan)
    assert result.level == "standard"


def test_compound_or_security_is_hard():
    compound = SimpleNamespace(agent="local_development", needs_tool=True, is_compound=True, confidence=0.9)
    assert ComplexityClassifier().classify("fix then test then report", compound).level == "hard"

    kali = SimpleNamespace(agent="kali", needs_tool=True, is_compound=False, confidence=0.96)
    assert ComplexityClassifier().classify("use nmap on my lab target", kali).level == "hard"


def test_debug_implement_keywords_are_hard():
    result = ComplexityClassifier().classify(
        "debug this failure and implement a fix across multiple files"
    )
    assert result.level == "hard"


def test_classifier_failure_returns_standard():
    class Boom:
        is_compound = True

        def __bool__(self):
            raise RuntimeError("boom")

    plan = SimpleNamespace(agent="research", needs_tool=False, is_compound=Boom(), confidence=0.4)
    result = ComplexityClassifier().classify("anything", plan)
    assert result.level == "standard"
    assert result.source == "fallback"


def test_single_research_query_is_standard_not_hard():
    from jenefar.core.planner import Planner

    plan = Planner().plan("what is the history of computers?")
    result = ComplexityClassifier().classify("what is the history of computers?", plan)
    assert plan.agent == "research"
    assert result.level == "standard"


def test_uncertain_heuristic_uses_llm_when_injected():
    plan = SimpleNamespace(agent="research", needs_tool=False, is_compound=False, confidence=0.55)

    def fake_llm(prompt: str) -> str:
        assert "classify" in prompt.lower() or "complexity" in prompt.lower()
        return '{"level": "hard", "reason": "broad research"}'

    result = ComplexityClassifier(llm_complete=fake_llm).classify(
        "what is the history of computers?",
        plan,
    )
    assert result.level == "hard"
    assert result.source == "llm"


def test_uncertain_llm_failure_stays_standard():
    plan = SimpleNamespace(agent="research", needs_tool=False, is_compound=False, confidence=0.55)

    def fake_llm(prompt: str) -> str:
        raise TimeoutError("offline")

    result = ComplexityClassifier(llm_complete=fake_llm).classify(
        "what is the history of computers?",
        plan,
    )
    assert result.level == "standard"


def test_tool_round_budget_by_complexity_and_agent_cap():
    assert tool_round_budget("simple", 4) == 4
    assert tool_round_budget("standard", 4) == 8
    assert tool_round_budget("hard", 4) == 16
    assert tool_round_budget("simple", 20) == 20
    assert tool_round_budget("hard", 20) == 20
    assert tool_round_budget("unknown", 4) == 8
