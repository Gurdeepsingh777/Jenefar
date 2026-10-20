from __future__ import annotations

import threading
from types import SimpleNamespace

from jenefar.voice.browser import BrowserVoiceBridge


class _Wakeword:
    @staticmethod
    def normalize_stt_text(value: str) -> str:
        return " ".join(value.casefold().split())


class _ActiveFuture:
    @staticmethod
    def done() -> bool:
        return False


def _busy_bridge():
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge.orchestrator = SimpleNamespace(wakeword=_Wakeword())
    bridge._last_text = ""
    bridge._last_at = 0.0
    bridge._repeat_window = 1.8
    bridge._active_task = _ActiveFuture()
    bridge._task_generation = 3
    bridge._task_lock = threading.RLock()
    bridge.events = []
    bridge._publish = lambda *args, **kwargs: bridge.events.append((args, kwargs))
    return bridge


def test_busy_typed_command_is_rejected_without_phantom_queued_events():
    bridge = _busy_bridge()

    result = bridge.submit_text("Open Firefox")

    assert result["accepted"] is False
    assert result["busy"] is True
    assert result["queued"] is False
    assert result["reason"] == "assistant_busy"
    assert bridge.events == []
    assert bridge._task_generation == 3


def test_busy_voice_command_does_not_publish_listening_or_queued_state():
    bridge = _busy_bridge()

    result = bridge.submit_text("check my IP")

    assert result["status"] == "busy"
    assert result["task_id"]
    assert bridge.events == []

def test_empty_or_whitespace_assistant_reply_is_not_treated_as_success():
    import pytest

    with pytest.raises(RuntimeError, match="empty response"):
        BrowserVoiceBridge._require_user_reply("   ")

    assert BrowserVoiceBridge._require_user_reply("Done.") == "Done."

def test_daemon_task_executor_stops_and_rejects_new_work_after_shutdown():
    from threading import Event
    import pytest

    from jenefar.voice.browser import _DaemonSingleWorkerExecutor

    entered = Event()
    release = Event()
    executor = _DaemonSingleWorkerExecutor(thread_name_prefix="jenefar-test")

    def active_work():
        entered.set()
        release.wait(2.0)
        return "finished"

    active = executor.submit(active_work)
    assert entered.wait(1.0)
    pending = executor.submit(lambda: "should be cancelled")
    assert executor._thread.daemon is True

    executor.shutdown(wait=False, cancel_futures=True)
    assert pending.cancelled()
    release.set()
    assert active.result(timeout=1.0) == "finished"
    executor.shutdown(wait=True)

    assert not executor._thread.is_alive()
    with pytest.raises(RuntimeError, match="after voice executor shutdown"):
        executor.submit(lambda: "late")


def test_voice_bridge_shutdown_is_idempotent_and_clears_queued_speech():
    from queue import Queue

    class Executor:
        def __init__(self):
            self.calls = []

        def shutdown(self, *, wait, cancel_futures):
            self.calls.append((wait, cancel_futures))

    class Thread:
        @staticmethod
        def is_alive():
            return False

    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge._task_lock = threading.RLock()
    bridge._shutdown_requested = False
    bridge._task_executor = Executor()
    bridge._speech_queue = Queue(maxsize=8)
    bridge._speech_thread = Thread()
    bridge._speech_queue.put_nowait(("old-task", "old speech"))

    bridge.shutdown()
    bridge.shutdown()

    assert bridge._shutdown_requested is True
    assert bridge._task_executor.calls == [(False, True)]
    assert bridge._speech_queue.qsize() == 1
    assert bridge._speech_queue.get_nowait() == ("__JENEFAR_SHUTDOWN__", "")
    bridge._speech_queue.task_done()


def test_submit_text_rejects_new_commands_after_shutdown():
    bridge = _busy_bridge()
    bridge._shutdown_requested = True

    result = bridge.submit_text("open Firefox")

    assert result["accepted"] is False
    assert result["status"] == "shutdown"
    assert bridge.events == []
