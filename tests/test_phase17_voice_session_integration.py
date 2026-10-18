from __future__ import annotations

from types import SimpleNamespace

from jenefar.voice.browser import BrowserVoiceBridge
from jenefar.voice.session_v2 import VoiceSession


class FakeWakeWord:
    def matched_phrase(self, _text):
        return None


class FakeOrchestrator:
    def __init__(self, *, fail=False):
        self.wakeword = FakeWakeWord()
        self.state = SimpleNamespace(name="AWAKE")
        self._latest_scan_result = None
        self.production = SimpleNamespace(voice=VoiceSession())
        self.fail = fail

    def handle(self, text, response_language=None):
        if self.fail:
            raise RuntimeError("controlled test error")
        return "Task complete: " + text


def build_bridge(orchestrator):
    bridge = object.__new__(BrowserVoiceBridge)
    bridge.orchestrator = orchestrator
    bridge.avatar = None
    bridge._last_assistant_text = ""
    bridge._last_assistant_spoken_at = 0.0
    bridge._publish = lambda *_args, **_kwargs: None
    bridge._synthesize_browser_audio = lambda _text: ("", "")
    return bridge


def test_browser_voice_task_closes_production_voice_turn():
    orchestrator = FakeOrchestrator()
    bridge = build_bridge(orchestrator)

    bridge._run_task("turn-1", "hello Jenefar")

    assert orchestrator.production.voice.active is None
    assert len(orchestrator.production.voice.history) == 1
    turn = orchestrator.production.voice.history[0]
    assert turn.turn_id == "turn-1"
    assert turn.transcript == "hello Jenefar"
    assert turn.ended_at is not None
    assert turn.interrupted is False


def test_browser_voice_task_closes_voice_turn_after_runtime_error():
    orchestrator = FakeOrchestrator(fail=True)
    bridge = build_bridge(orchestrator)

    bridge._run_task("turn-error", "do a test")

    assert orchestrator.production.voice.active is None
    assert len(orchestrator.production.voice.history) == 1
    assert orchestrator.production.voice.history[0].ended_at is not None
