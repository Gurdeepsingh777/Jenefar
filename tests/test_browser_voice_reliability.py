import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from types import SimpleNamespace

from jenefar.voice.browser import BrowserVoiceBridge


def make_bridge():
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge._speech_queue = Queue(maxsize=8)
    bridge._tts_lock = threading.Lock()
    bridge._shutdown_event = threading.Event()
    bridge._tts_openai_disabled_until = 0.0
    bridge._tts_openai_cooldown_seconds = 3600.0
    bridge._task_executor = ThreadPoolExecutor(max_workers=1)
    bridge._speech_thread = threading.Thread(
        target=lambda: None,
        daemon=True,
    )
    return bridge


def test_shutdown_is_idempotent():
    bridge = make_bridge()

    bridge.shutdown()
    bridge.shutdown()

    assert bridge._shutdown_event.is_set()


def test_quota_error_disables_openai_and_uses_edge(monkeypatch):
    bridge = make_bridge()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeSpeech:
        def create(self, **kwargs):
            raise RuntimeError(
                "429 insufficient_quota credit_balance_exhausted"
            )

    class FakeAudio:
        speech = FakeSpeech()

    class FakeClient:
        audio = FakeAudio()

    import openai

    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda api_key: FakeClient(),
    )

    monkeypatch.setattr(
        bridge,
        "_synthesize_edge_audio",
        lambda text: ("fallback", "audio/mpeg"),
    )

    audio, mime = bridge._synthesize_browser_audio("hello")

    assert audio == "fallback"
    assert mime == "audio/mpeg"
    assert bridge._tts_openai_disabled_until > time.monotonic()

    bridge.shutdown()


def test_openai_is_skipped_during_quota_cooldown(monkeypatch):
    bridge = make_bridge()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    bridge._tts_openai_disabled_until = time.monotonic() + 3600

    import openai

    def should_not_run(*args, **kwargs):
        raise AssertionError(
            "OpenAI TTS should be skipped during cooldown"
        )

    monkeypatch.setattr(
        openai,
        "OpenAI",
        should_not_run,
    )

    monkeypatch.setattr(
        bridge,
        "_synthesize_edge_audio",
        lambda text: ("fallback", "audio/mpeg"),
    )

    audio, mime = bridge._synthesize_browser_audio("hello")

    assert audio == "fallback"
    assert mime == "audio/mpeg"

    bridge.shutdown()


def test_browser_tts_returns_empty_after_shutdown():
    bridge = make_bridge()

    bridge._shutdown_event.set()

    assert bridge._synthesize_browser_audio("hello") == ("", "")

    bridge.shutdown()
