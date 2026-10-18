from __future__ import annotations

import base64
import threading
from concurrent.futures import Future
from queue import Queue

from jenefar.voice.browser import BrowserVoiceBridge


def _audio_response_payload():
    return {
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "audio",
                        "data": base64.b64encode(b"RIFF-test-audio").decode("ascii"),
                        "mime_type": "audio/wav",
                    }
                ],
            }
        ]
    }


def test_gemini_tts_requests_style_and_returns_generated_audio(monkeypatch):
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("JENEFAR_GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
    monkeypatch.setenv("JENEFAR_GEMINI_TTS_VOICE", "Aoede")
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return _audio_response_payload()

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    encoded, mime = bridge._synthesize_gemini_audio("Haan, main samajh sakti hoon. Chinta mat karo.")

    assert base64.b64decode(encoded) == b"RIFF-test-audio"
    assert mime == "audio/wav"
    assert captured["url"].endswith("/v1beta/interactions")
    payload = captured["json"]
    assert payload["model"] == "gemini-3.8-flash-tts"
    assert payload["generation_config"]["speech_config"] == [{"voice": "Aoede"}]
    annotation = payload["input"][0]["content"][0]["annotations"][0]
    assert annotation["type"] == "speech_metadata"
    assert "empathetic" in annotation["style"].lower()


def test_browser_tts_tries_gemini_before_edge_when_openai_key_is_missing(monkeypatch):
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge._openai_tts_disabled = False
    called = {"edge": 0}

    class Response:
        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return _audio_response_payload()

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: Response())

    def edge(_text):
        called["edge"] += 1
        return "", ""

    monkeypatch.setattr(BrowserVoiceBridge, "_synthesize_edge_audio", edge)
    audio, mime = bridge._synthesize_browser_audio("Kya tum meri madad karogi?")

    assert audio
    assert mime == "audio/wav"
    assert called["edge"] == 0


def test_gemini_tts_style_changes_for_questions_and_reassurance():
    reassurance = BrowserVoiceBridge._gemini_tts_style("I understand. Sorry, chinta mat karo.")
    question = BrowserVoiceBridge._gemini_tts_style("Kya main tumhari madad kar sakti hoon?")
    celebration = BrowserVoiceBridge._gemini_tts_style("Congratulations, bahut achha!")
    assert "empathetic" in reassurance.lower()
    assert "curious" in question.lower()
    assert "happy" in celebration.lower()



def test_gemini_tts_quota_error_disables_repeated_calls_until_restart(monkeypatch):
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge._gemini_tts_disabled = False
    calls = []

    def rate_limited_post(url, **_kwargs):
        calls.append(url)
        raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED: quota exceeded")

    monkeypatch.setattr(httpx, "post", rate_limited_post)

    assert bridge._synthesize_gemini_audio("Hello") == ("", "")
    assert bridge._gemini_tts_disabled is True
    assert bridge._synthesize_gemini_audio("Hello again") == ("", "")
    assert len(calls) == 1



def test_dashboard_approval_defers_to_an_active_spoken_confirmation():
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge._active_task = Future()
    bridge._last_text = "yes"

    class Orchestrator:
        @staticmethod
        def _confirmation_choice(text):
            return "yes" if text.strip().lower() == "yes" else None

        @staticmethod
        def _approve_pending(_pending_id):
            raise AssertionError("dashboard must not race the active voice approval")

    bridge.orchestrator = Orchestrator()

    result = bridge.approve_pending("pending-1")

    assert result["status"] == "ok"
    assert result["speech_owner"] == "voice_confirmation"


def test_duplicate_dashboard_approval_queues_speech_only_once():
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge._active_task = None
    bridge._last_text = ""
    bridge._approval_voice_lock = threading.Lock()
    bridge._approval_voice_results = {}
    bridge._speech_queue = Queue(maxsize=8)
    published = []
    bridge._publish = lambda *args, **kwargs: published.append((args, kwargs))

    class Orchestrator:
        def __init__(self):
            self.approve_calls = 0

        @staticmethod
        def _confirmation_choice(_text):
            return None

        def _approve_pending(self, pending_id):
            assert pending_id == "pending-1"
            self.approve_calls += 1
            return "Host discovery complete: 4 hosts online."

    orchestrator = Orchestrator()
    bridge.orchestrator = orchestrator

    first = bridge.approve_pending("pending-1")
    second = bridge.approve_pending("pending-1")

    assert first["result"] == second["result"]
    assert second["duplicate"] is True
    assert orchestrator.approve_calls == 1
    assert bridge._speech_queue.qsize() == 1
    assert len(published) == 1
