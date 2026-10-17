from __future__ import annotations

import asyncio
import io
import sys
from types import SimpleNamespace

from jenefar.voice.provider import ProviderVoiceRuntime


def test_local_whisper_transcription_uses_cached_model_and_configured_language(monkeypatch):
    captured = {}

    class FakeWhisperModel:
        def __init__(self, model, **kwargs):
            captured["model"] = model
            captured["init"] = kwargs

        def transcribe(self, audio, **kwargs):
            captured["transcribe"] = kwargs
            assert audio.read()
            return iter([
                SimpleNamespace(text=" Hello Jenefar "),
                SimpleNamespace(text=" meri awaaz suno "),
            ]), SimpleNamespace(language="hi")

    monkeypatch.setitem(
        sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel)
    )
    monkeypatch.setenv("JENEFAR_LOCAL_STT_MODEL", "small")
    monkeypatch.delenv("JENEFAR_LOCAL_STT_MODEL_PATH", raising=False)
    monkeypatch.setenv("JENEFAR_LOCAL_STT_DEVICE", "cpu")
    monkeypatch.setenv("JENEFAR_LOCAL_STT_COMPUTE_TYPE", "int8")
    monkeypatch.setenv("JENEFAR_LOCAL_STT_LANGUAGE", "hi")

    runtime = ProviderVoiceRuntime(object())
    transcript = asyncio.run(runtime._transcribe_local(io.BytesIO(b"wav-buffer")))

    assert transcript == "Hello Jenefar meri awaaz suno"
    assert captured["model"] == "small"
    assert captured["init"] == {
        "device": "cpu",
        "compute_type": "int8",
        "local_files_only": True,
    }
    assert captured["transcribe"]["language"] == "hi"
    assert captured["transcribe"]["vad_filter"] is True


def test_local_whisper_fallback_runs_when_no_cloud_stt_is_configured(monkeypatch):
    runtime = ProviderVoiceRuntime(object())
    monkeypatch.setattr(runtime, "_provider_order", lambda: [])

    async def local_transcription(_audio):
        return "offline transcript"

    monkeypatch.setattr(runtime, "_transcribe_local", local_transcription)

    transcript = asyncio.run(runtime.transcribe_pcm(b"\x00" * 3200))

    assert transcript == "offline transcript"


def test_local_whisper_fallback_runs_after_online_provider_exhaustion(monkeypatch):
    runtime = ProviderVoiceRuntime(object())
    monkeypatch.setattr(runtime, "_provider_order", lambda: ["openai"])
    monkeypatch.setattr(runtime._audio_pool, "available", lambda _provider: True)

    async def exhausted_openai(_audio):
        raise RuntimeError("credit_balance_exhausted: insufficient_quota")

    async def local_transcription(_audio):
        return "local transcript after quota error"

    monkeypatch.setattr(runtime, "_transcribe_openai", exhausted_openai)
    monkeypatch.setattr(runtime, "_transcribe_local", local_transcription)

    transcript = asyncio.run(runtime.transcribe_pcm(b"\x00" * 3200))

    assert transcript == "local transcript after quota error"


def test_missing_local_whisper_dependency_has_actionable_error(monkeypatch):
    runtime = ProviderVoiceRuntime(object())
    monkeypatch.setitem(sys.modules, "faster_whisper", None)

    try:
        runtime._get_local_stt_model()
    except RuntimeError as exc:
        assert "python -m pip install faster-whisper" in str(exc)
    else:
        raise AssertionError("Expected missing faster-whisper to be reported.")
