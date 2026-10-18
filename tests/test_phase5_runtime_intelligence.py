from pathlib import Path

from jenefar.evaluation.loop import EvaluationLoop
from jenefar.evaluation.trace import ExecutionTrace, TraceStore


def test_execution_trace_records_success_and_latency(tmp_path):
    trace = ExecutionTrace(
        session_id="session-1",
        task="test task",
        source="user",
        intent="research",
        planned_agent="research",
        actual_agent="research",
        planner_confidence=0.8,
    )
    trace.add_tool_call(name="example_tool", status="success")
    trace.finish(
        status="success",
        provider="test",
        verification={"passed": True},
    )
    assert trace.elapsed_ms() is not None
    assert trace.as_dict()["status"] == "success"
    assert trace.as_dict()["verification"]["passed"] is True


def test_trace_store_summary(tmp_path):
    store = TraceStore(tmp_path / "traces.jsonl")
    trace = ExecutionTrace(session_id="s", task="task", actual_agent="python")
    trace.finish(status="success", provider="local", verification={"passed": True})
    store.append(trace)

    summary = store.summary()
    assert summary["traces"] == 1
    assert summary["success_rate"] == 1.0
    assert summary["providers"] == ["local"]
    assert summary["agents"] == ["python"]


def test_evaluation_uses_trace_failure_signals(tmp_path):
    evaluator = EvaluationLoop(tmp_path / "eval.jsonl")
    result = evaluator.evaluate(
        "do task",
        "done",
        provider="local",
        trace={
            "trace_id": "t1",
            "session_id": "s1",
            "status": "error",
            "verification": {"passed": False},
            "errors": ["boom"],
            "tool_calls": [{"name": "x", "status": "error"}],
            "elapsed_ms": 50,
            "actual_agent": "python",
        },
    )
    assert result.score < 1.0
    assert "runtime_error_signal" in result.reasons
    assert "verification_failed" in result.reasons
    assert "tool_error" in result.reasons

    records = evaluator.recent()
    assert records[0]["trace_id"] == "t1"
    assert records[0]["agent"] == "python"


def test_shortcut_orchestrator_requests_are_traced(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from jenefar.core.orchestrator import JenefarOrchestrator
    from jenefar.core.state import JenefarState

    class FakeSession:
        session_id = "shortcut-session"
        messages = []

        def add(self, *_args, **_kwargs):
            pass

    class FakeMemory:
        def record_message(self, *_args, **_kwargs):
            pass

    class FakeGraph:
        def learn_text(self, *_args, **_kwargs):
            pass

    orchestrator = JenefarOrchestrator.__new__(JenefarOrchestrator)
    orchestrator.session = FakeSession()
    orchestrator.memory_engine = FakeMemory()
    orchestrator.graph = FakeGraph()
    orchestrator.config = SimpleNamespace(single_turn_sleep=False)
    orchestrator.state = JenefarState.AWAKE
    orchestrator.avatar = None
    orchestrator.evaluator = EvaluationLoop(tmp_path / "eval.jsonl")
    orchestrator.trace_store = TraceStore(tmp_path / "traces.jsonl")
    orchestrator._latest_scan_result = None

    monkeypatch.setattr(orchestrator, "_handle_conversational_confirmation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orchestrator, "_is_local_host_port_scan_request", lambda _text: False)
    monkeypatch.setattr(orchestrator, "_is_local_host_discovery_request", lambda _text: False)
    monkeypatch.setattr(orchestrator, "_direct_window_transfer", lambda _text: None)
    monkeypatch.setattr(orchestrator, "_direct_screen_read", lambda _text: None)
    monkeypatch.setattr(orchestrator, "_is_ip_info_query", lambda _text: True)
    monkeypatch.setattr(orchestrator, "_local_ip_info_response", lambda: "Local IP: 192.0.2.10")
    monkeypatch.setattr(orchestrator, "_avatar_state", lambda *_args, **_kwargs: None)

    assert orchestrator.handle("check my IP") == "Local IP: 192.0.2.10"

    records = orchestrator.trace_store.recent()
    assert len(records) == 1
    assert records[0]["intent"] == "local_ip_info"
    assert records[0]["actual_agent"] == "local_runtime"
    assert records[0]["status"] == "success"
    assert records[0]["verification"]["passed"] is True
    evaluations = orchestrator.evaluator.recent()
    assert evaluations[0]["trace_id"] == records[0]["trace_id"]


def test_orchestrator_trace_captures_successful_tool_names_and_retry_delta():
    source = (Path(__file__).resolve().parents[1] / "jenefar" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert 'for action in task_actions:' in source
    assert 'name=str(action.get("tool") or "unknown")' in source
    assert '"retries": self.self_healing.health.retries - retry_count_before' in source
    assert '"retry_safe": plan.agent == "research"' in source
