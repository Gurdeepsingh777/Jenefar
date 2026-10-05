from __future__ import annotations

import time

from jenefar.evaluation.runtime_status import build_runtime_snapshot


class FakeHealth:
    def health_snapshot(self):
        return {
            "calls": 4,
            "successes": 3,
            "failures": 1,
            "success_rate": 0.75,
            "retries": 1,
            "circuit_open": False,
        }


class FakePool:
    def latency_status(self):
        return {"groq": {"samples": 2, "average_ms": 120.0}}


def test_runtime_snapshot_reports_live_deadline_and_health():
    snapshot = build_runtime_snapshot(
        runtime_context={
            "state": "thinking",
            "task_id": "abc123",
            "task": "test runtime",
            "agent": "python",
            "provider": "groq",
            "model_role": "fast",
            "started_at": time.time() - 1.0,
            "budget_seconds": 60.0,
            "deadline_monotonic": time.monotonic() + 59.0,
            "last_event": "dispatch_started",
        },
        self_healing=FakeHealth(),
        provider_pool=FakePool(),
    )
    assert snapshot["schema_version"] == 1
    assert snapshot["current"]["state"] == "thinking"
    assert snapshot["current"]["task_id"] == "abc123"
    assert 0 < snapshot["current"]["remaining_seconds"] <= 60
    assert snapshot["health"]["success_rate"] == 0.75
    assert "groq" in snapshot["providers"]


def test_runtime_snapshot_is_safe_when_idle():
    snapshot = build_runtime_snapshot(runtime_context={"state": "idle"})
    assert snapshot["current"]["state"] == "idle"
    assert snapshot["current"]["remaining_seconds"] is None
    assert snapshot["current"]["deadline_active"] is False


def test_runtime_snapshot_bounds_elapsed_and_timeout_values():
    snapshot = build_runtime_snapshot(runtime_context={"started_at": time.time() - 0.1})
    assert snapshot["current"]["elapsed_ms"] >= 0
    assert snapshot["timeouts"]["provider_seconds"] >= 5
