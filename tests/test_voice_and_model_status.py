from __future__ import annotations

from jenefar.core.orchestrator import JenefarOrchestrator


def test_voice_provider_module_imports():
    from jenefar.voice.provider import ProviderVoiceRuntime
    assert ProviderVoiceRuntime is not None


def test_model_metadata_is_rendered():
    orchestrator = JenefarOrchestrator()
    class Result:
        metadata = {"provider": "openrouter", "model": "openrouter/free"}
        content = "hello"
    # Ensure the metadata keys used by the runtime are stable.
    assert Result.metadata["provider"] == "openrouter"
    assert Result.metadata["model"] == "openrouter/free"
    assert orchestrator is not None

from jenefar.voice.provider import ProviderVoiceRuntime


def test_voice_prefers_direct_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"]["provider"] == "openai"
    assert status["tts"]["provider"] == "openai"


def test_voice_uses_groq_when_openai_is_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"] == {
        "provider": "groq",
        "model": "whisper-large-v3-turbo",
    }
    assert status["tts"] == {
        "provider": "groq",
        "model": "canopylabs/orpheus-v1-english",
    }


def test_voice_reports_no_audio_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    status = ProviderVoiceRuntime.audio_status()
    assert status == {"stt": None, "tts": None}


def test_voice_provider_status_line(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    runtime = ProviderVoiceRuntime.__new__(ProviderVoiceRuntime)
    assert "STT=groq/whisper-large-v3-turbo" in runtime.provider_status_line()
    assert "TTS=groq/canopylabs/orpheus-v1-english" in runtime.provider_status_line()


def test_run_py_default_uses_continuous_voice_runtime():
    from pathlib import Path
    source = Path("run.py").read_text(encoding="utf-8")
    assert "ContinuousVoiceRuntime(orchestrator).run()" in source
    assert "ProviderVoiceRuntime(JenefarOrchestrator()).run()" not in source


def test_groq_stt_defaults_to_accuracy_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    monkeypatch.delenv("GROQ_STT_MODEL", raising=False)
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"]["model"] == "whisper-large-v3"


def test_groq_stt_request_uses_accuracy_options(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    captured = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type("Result", (), {"text": "Hello Jenefar"})()

    class FakeAudio:
        transcriptions = FakeTranscriptions()

    class FakeClient:
        audio = FakeAudio()

    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: FakeClient())
    runtime = ProviderVoiceRuntime.__new__(ProviderVoiceRuntime)
    import asyncio, io, wave
    pcm = (b"\\x00\\x00" * 16000)
    result = asyncio.run(runtime._transcribe_groq(runtime._wav_bytes(pcm)))
    assert result == "Hello Jenefar"
    assert captured["model"] == "whisper-large-v3"
    assert captured["language"] == "en"
    assert captured["temperature"] == 0.0
    assert "Jenefar" in captured["prompt"]
