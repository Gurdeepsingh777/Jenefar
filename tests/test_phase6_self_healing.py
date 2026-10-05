import pytest

from jenefar.core.self_healing import RetryPolicy, SelfHealingRuntime


def test_transient_failure_is_retried():
    runtime = SelfHealingRuntime(policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0))
    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("temporary timeout")
        return "ok"

    assert runtime.run("research_fetch", operation) == "ok"
    assert attempts["count"] == 2
    assert runtime.health.retries == 1
    assert runtime.health.successes == 1


def test_approval_gated_action_is_not_retried():
    runtime = SelfHealingRuntime(policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0))
    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        raise TimeoutError("temporary timeout")

    with pytest.raises(TimeoutError):
        runtime.run("workspace_edit_file", operation, metadata={"approval_required": True})

    assert attempts["count"] == 1
    assert runtime.health.retries == 0


def test_security_dispatch_is_not_retried():
    runtime = SelfHealingRuntime(policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0))
    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        raise ConnectionError("connection reset")

    with pytest.raises(ConnectionError):
        runtime.run("agent_dispatch", operation, metadata={"security_action": True})

    assert attempts["count"] == 1


def test_circuit_opens_after_repeated_failures():
    runtime = SelfHealingRuntime(
        policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        circuit_threshold=2,
        circuit_cooldown_seconds=60,
    )

    for _ in range(2):
        with pytest.raises(ConnectionError):
            runtime.run("research_fetch", lambda: (_ for _ in ()).throw(ConnectionError("service unavailable")))

    assert runtime.health.circuit_open

    with pytest.raises(RuntimeError, match="runtime circuit open"):
        runtime.run("research_fetch", lambda: "should not execute")


def test_health_snapshot_redacts_errors_and_exposes_circuit_state():
    runtime = SelfHealingRuntime(
        policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        circuit_threshold=1,
        circuit_cooldown_seconds=60,
    )

    with pytest.raises(ConnectionError):
        runtime.run(
            "research_fetch",
            lambda: (_ for _ in ()).throw(ConnectionError("token=sk-secret-value")),
        )

    snapshot = runtime.health_snapshot()
    assert snapshot["failures"] == 1
    assert snapshot["circuit_open"] is True
    assert "sk-secret-value" not in str(snapshot)
    assert "[REDACTED" in snapshot["last_error"]

    runtime.reset_circuit()
    assert runtime.health.circuit_open is False
    assert runtime.health.failures == 1
