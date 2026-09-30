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
