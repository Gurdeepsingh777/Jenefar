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


def test_trace_redacts_credentials_and_bounds_large_payload():
    trace = ExecutionTrace(
        session_id="s",
        task="send token=sk-test_12345678901234567890",
    )
    trace.add_tool_call(
        name="demo",
        status="success",
        result={
            "authorization": "Bearer super-secret-token",
            "body": "x" * 5000,
        },
    )
    trace.add_error("api_key=sk-live_12345678901234567890")
    payload = trace.as_dict()

    serialized = str(payload)
    assert "super-secret-token" not in serialized
    assert "sk-live_12345678901234567890" not in serialized
    assert "[TRUNCATED]" in serialized
    assert "[REDACTED" in serialized or "[REDACTED]" in serialized


def test_trace_store_ignores_malformed_json_and_reports_failures(tmp_path):
    path = tmp_path / "traces.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")
    store = TraceStore(path)

    failed = ExecutionTrace(session_id="s", task="failed", actual_agent="research")
    failed.finish(status="error", provider="local", verification={"passed": False})
    store.append(failed)

    approval = ExecutionTrace(session_id="s", task="approval", actual_agent="utility")
    approval.add_tool_call(
        name="write_file",
        status="approval_required",
        approval_required=True,
    )
    approval.finish(status="awaiting_approval", provider="local")
    store.append(approval)

    records = store.recent()
    assert len(records) == 2

    summary = store.summary()
    assert summary["traces"] == 2
    assert summary["failure_rate"] == 0.5
    assert summary["approval_traces"] == 1
    assert summary["statuses"]["awaiting_approval"] == 1
    assert summary["statuses"]["error"] == 1
    assert summary["last_status"] == "awaiting_approval"


def test_evaluation_record_redacts_sensitive_task(tmp_path):
    evaluator = EvaluationLoop(tmp_path / "eval.jsonl")
    evaluator.evaluate(
        "login with token=sk-test_12345678901234567890",
        "done",
        provider="local",
    )

    raw = (tmp_path / "eval.jsonl").read_text(encoding="utf-8")
    assert "sk-test_12345678901234567890" not in raw
    assert "[REDACTED" in raw or "[REDACTED]" in raw
