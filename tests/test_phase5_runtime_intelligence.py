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
