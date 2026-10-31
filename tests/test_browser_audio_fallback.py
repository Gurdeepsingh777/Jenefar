from __future__ import annotations

import asyncio
import io

from jenefar.voice.browser import BrowserVoiceBridge


def test_browser_audio_fallback_transcribes_and_submits(monkeypatch):
    from jenefar.voice.provider import ProviderVoiceRuntime

    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    bridge.submit_text = lambda text: {"ok": True, "accepted": True, "text": text}

    monkeypatch.setattr(ProviderVoiceRuntime, "_configured_audio_providers", staticmethod(lambda: ["groq"]))
    async def fake_transcribe(audio):
        assert audio.name.endswith(".webm")
        assert audio.read() == b"fake-audio"
        return "hello Jenefar"
    monkeypatch.setattr(ProviderVoiceRuntime, "_transcribe_groq", staticmethod(fake_transcribe))

    result = bridge.handle_audio(b"fake-audio", "audio/webm;codecs=opus")
    assert result["ok"] is True
    assert result["transcript"] == "hello Jenefar"
    assert result["stt_provider"] == "groq"


def test_browser_audio_fallback_requires_configured_stt_provider(monkeypatch):
    from jenefar.voice.provider import ProviderVoiceRuntime

    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    monkeypatch.setattr(ProviderVoiceRuntime, "_configured_audio_providers", staticmethod(lambda: []))
    result = bridge.handle_audio(b"fake-audio", "audio/webm")
    assert result["ok"] is False
    assert "GROQ_API_KEY" in result["error"]


def test_browser_audio_fallback_rejects_empty_or_oversized_payload():
    bridge = BrowserVoiceBridge.__new__(BrowserVoiceBridge)
    assert bridge.handle_audio(b"")["ok"] is False
    assert bridge.handle_audio(b"x" * (8 * 1024 * 1024 + 1))["ok"] is False
