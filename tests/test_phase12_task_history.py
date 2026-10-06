from __future__ import annotations

import threading

from jenefar.core.task_lifecycle import TaskLifecycle


def test_task_history_persists_terminal_records(tmp_path):
    path = tmp_path / "task-history.jsonl"
    first = TaskLifecycle(history_path=path, max_history=10)
    first.admit("task-1", "hello token=super-secret", agent="python")
    first.transition("task-1", "running")
    first.transition("task-1", "completed", provider="groq")

    second = TaskLifecycle(history_path=path, max_history=10)
    items = second.history(10)
    assert len(items) == 1
    assert items[0]["task_id"] == "task-1"
    assert items[0]["state"] == "completed"
    assert "[REDACTED]" in items[0]["task"]
    assert "super-secret" not in path.read_text(encoding="utf-8")


def test_task_history_is_bounded_and_filters(tmp_path):
    path = tmp_path / "history.jsonl"
    lifecycle = TaskLifecycle(history_path=path, max_history=2)
    for index, (state, agent) in enumerate(
        [("completed", "python"), ("failed", "research"), ("cancelled", "python")]
    ):
        lifecycle.admit(f"task-{index}", f"job {index}", agent=agent)
        lifecycle.transition(f"task-{index}", state, provider="groq")

    assert [item["task_id"] for item in lifecycle.history(10)] == ["task-2", "task-1"]
    assert lifecycle.history(10, state="failed")[0]["task_id"] == "task-1"
    assert lifecycle.history(10, agent="python")[0]["task_id"] == "task-2"
    assert lifecycle.history(10, search="job 2")[0]["task_id"] == "task-2"


def test_task_history_concurrent_admission_stays_single_active(tmp_path):
    lifecycle = TaskLifecycle(history_path=tmp_path / "history.jsonl")
    results = []

    def admit(index):
        results.append(lifecycle.admit(f"task-{index}", str(index)) is not None)

    threads = [threading.Thread(target=admit, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results) == 1


def test_task_history_snapshot_exposes_persistence(tmp_path):
    lifecycle = TaskLifecycle(history_path=tmp_path / "history.jsonl")
    assert lifecycle.snapshot()["history_persistent"] is True
    assert lifecycle.snapshot()["history_limit"] >= 1
