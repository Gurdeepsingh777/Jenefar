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
