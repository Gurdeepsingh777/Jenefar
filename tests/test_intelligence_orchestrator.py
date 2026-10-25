from jenefar.core.agent import AgentResult
from jenefar.core.intent import LLMIntentFallback
from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.core.planner import Plan
from jenefar.critic.verifier import Critique, Verifier
from jenefar.evaluation.trace import ExecutionTrace


class RecordingRouter:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def dispatch(self, text, *, metadata=None):
        self.calls.append({"text": text, "metadata": dict(metadata or {})})
        if self.results:
            return self.results.pop(0)
        return AgentResult(agent="research", content="done", metadata={"provider": "fake"})


def test_low_confidence_plan_triggers_intent_fallback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    orchestrator = JenefarOrchestrator()
    calls = []

    def fake_llm(prompt: str) -> str:
        calls.append(prompt)
        return '{"intent": "python", "agent": "python", "needs_tool": false, "reason": "language question"}'

    orchestrator.intent_fallback = LLMIntentFallback(llm_complete=fake_llm)
    orchestrator.router = RecordingRouter([
        AgentResult(agent="python", content="Python is a programming language.", metadata={"provider": "fake"}),
    ])

    output = orchestrator.handle("what is the history of computers?")
    assert "Python" in output or output
    assert calls, "low-confidence research fallback should call intent LLM"
    assert orchestrator.router.calls[0]["metadata"]["planned_agent"] == "python"
    assert orchestrator.router.calls[0]["metadata"]["intent_fallback_used"] is True


def test_hard_task_critic_fail_replans_once(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    orchestrator = JenefarOrchestrator()
    orchestrator.intent_fallback = LLMIntentFallback(llm_complete=None)
    orchestrator.router = RecordingRouter([
        AgentResult(
            agent="local_development",
            content="I updated example.py and the tests passed.",
            metadata={"provider": "fake"},
        ),
        AgentResult(
            agent="local_development",
            content="Edited example.py after critic notes.",
            metadata={"provider": "fake"},
        ),
    ])
    reviews = []

    class CountingVerifier(Verifier):
        def review(self, task, result, *, complexity="standard", tool_trace=None):
            reviews.append(result)
            if len(reviews) == 1:
                return Critique(False, "claimed file without tool")
            return Critique(True, "ok")

    orchestrator.verifier = CountingVerifier()
    output = orchestrator.handle("debug this failure and implement a fix across multiple files")
    assert len(orchestrator.router.calls) == 2
    assert orchestrator.router.calls[1]["metadata"]["critic_pass"] == 1
    assert "claimed file" in orchestrator.router.calls[1]["metadata"]["critic_notes"]
    assert "Edited example.py" in output
    assert len(reviews) >= 1


def test_simple_task_skips_critic_replan(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    orchestrator = JenefarOrchestrator()
    orchestrator.intent_fallback = LLMIntentFallback(llm_complete=None)
    orchestrator.router = RecordingRouter([
        AgentResult(agent="utility", content="Haan, time bata deti hoon.", metadata={"provider": "fake"}),
    ])
    orchestrator.verifier = Verifier()
    # Bypass the deterministic time shortcut so the intelligence path runs.
    orchestrator._is_local_time_query = lambda text: False
    orchestrator.handle("hi")
    assert len(orchestrator.router.calls) == 1
    assert orchestrator.router.calls[0]["metadata"]["complexity"] == "simple"


def test_trace_records_intelligence_fields(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    store_path = tmp_path / "traces.jsonl"
    orchestrator = JenefarOrchestrator()
    orchestrator.trace_store.path = store_path
    orchestrator.intent_fallback = LLMIntentFallback(llm_complete=None)
    orchestrator.router = RecordingRouter([
        AgentResult(
            agent="research",
            content="Computers started as calculating machines.",
            metadata={"provider": "fake", "model": "test-model"},
        ),
    ])
    orchestrator.handle("what is the history of computers?")
    records = orchestrator.trace_store.recent(1)
    assert records
    record = records[0]
    assert record.get("complexity") in {"simple", "standard", "hard"}
    assert "model_role" in record
    assert "critic_verdict" in record
    assert "critic_replan" in record
    assert "intent_fallback_used" in record


def test_execution_trace_defaults_include_intelligence_fields():
    trace = ExecutionTrace(task="x")
    payload = trace.as_dict()
    assert payload["complexity"] == ""
    assert payload["intent_fallback_used"] is False
    assert payload["critic_verdict"] == ""
    assert payload["critic_replan"] is False
