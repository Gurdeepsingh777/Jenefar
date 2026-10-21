import threading

from jenefar.core.task_lifecycle import TaskLifecycle


def test_task_lifecycle_admits_one_active_task_and_blocks_second():
    lifecycle = TaskLifecycle()
    first = lifecycle.admit("task-1", "first", agent="python")
    second = lifecycle.admit("task-2", "second", agent="research")
    assert first is not None
    assert second is None
    assert lifecycle.active()["task_id"] == "task-1"


def test_task_lifecycle_transitions_and_clears_active_task():
    lifecycle = TaskLifecycle()
    lifecycle.admit("task-1", "first")
    lifecycle.transition("task-1", "running")
    lifecycle.transition("task-1", "waiting_approval", reason="approval_required")
    current = lifecycle.active()
    assert current["state"] == "waiting_approval"
    lifecycle.transition("task-1", "completed", provider="groq")
    assert lifecycle.active() is None
    assert lifecycle.history(1)[0]["state"] == "completed"


def test_task_lifecycle_cancel_is_terminal_and_next_task_can_start():
    lifecycle = TaskLifecycle()
    lifecycle.admit("task-1", "first")
    lifecycle.transition("task-1", "cancelling", reason="user stop")
    lifecycle.transition("task-1", "cancelled", reason="Jenefar execution cancelled")
    assert lifecycle.active() is None
    assert lifecycle.admit("task-2", "second") is not None


def test_task_lifecycle_is_thread_safe_for_admission():
    lifecycle = TaskLifecycle()
    results = []

    def admit(index):
        results.append(lifecycle.admit(f"task-{index}", str(index)) is not None)

    threads = [threading.Thread(target=admit, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results) == 1


def test_orchestrator_runtime_snapshot_exposes_task_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("JENEFAR_TASK_HISTORY_PATH", str(tmp_path / "task-history.jsonl"))
    from jenefar.core.orchestrator import JenefarOrchestrator

    orchestrator = JenefarOrchestrator()
    snapshot = orchestrator.runtime_status()
    assert snapshot["tasks"]["active"] is None
    assert snapshot["tasks"]["active_count"] == 0
    assert snapshot["tasks"]["history"] == []

def test_orchestrator_activity_events_inherit_and_reset_voice_task_id():
    import threading
    from jenefar.core.orchestrator import JenefarOrchestrator

    class Avatar:
        def __init__(self):
            self.events = []

        def publish(self, state, text="", **kwargs):
            self.events.append({"state": state, "text": text, **kwargs})

    orchestrator = object.__new__(JenefarOrchestrator)
    orchestrator.avatar = Avatar()
    orchestrator._avatar_event_task = threading.local()

    previous = orchestrator.bind_avatar_event_task("voice-task-123")
    orchestrator._avatar_activity("thinking", "Planning current request")
    orchestrator.reset_avatar_event_task(previous)
    orchestrator._avatar_activity("idle", "Ready")

    assert orchestrator.avatar.events[0]["task_id"] == "voice-task-123"
    assert orchestrator.avatar.events[1]["task_id"] == ""
