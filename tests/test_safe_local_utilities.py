from __future__ import annotations

from jenefar.core.orchestrator import JenefarOrchestrator


def test_time_query_is_deterministic():
    orch = JenefarOrchestrator()
    assert orch._is_local_time_query("abhi time kya huaa h")
    assert orch._is_local_time_query("check laptop me time")
    assert not orch._is_local_time_query("what is the execution time of this script")


def test_local_time_response_contains_time():
    orch = JenefarOrchestrator()
    response = orch._local_time_response("abhi time kya huaa h")
    assert "Abhi aapke laptop ka local time" in response
    assert "(" in response and ")" in response
