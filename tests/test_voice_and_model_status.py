from __future__ import annotations

import asyncio

from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.voice.provider import ProviderVoiceRuntime


def test_voice_provider_module_imports():
    assert ProviderVoiceRuntime is not None


def test_model_metadata_is_rendered():
    orchestrator = JenefarOrchestrator()

    class Result:
        metadata = {"provider": "openrouter", "model": "openrouter/free"}
        content = "hello"

    assert Result.metadata["provider"] == "openrouter"
    assert Result.metadata["model"] == "openrouter/free"
    assert orchestrator is not None


def test_voice_prefers_direct_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    monkeypatch.setenv("JENEFAR_VOICE_PROVIDER_ORDER", "openai,groq")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"]["provider"] == "openai"
    assert status["stt"]["fallback"] == ["groq"]
    assert status["tts"]["provider"] == "openai"
    assert status["tts"]["fallback"] == ["groq"]


def test_voice_can_prefer_groq(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    monkeypatch.setenv("JENEFAR_VOICE_PROVIDER_ORDER", "groq,openai")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"]["provider"] == "groq"
    assert status["stt"]["fallback"] == ["openai"]


def test_voice_uses_groq_when_openai_is_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"] == {
        "provider": "groq",
        "model": "whisper-large-v3",
        "fallback": [],
    }
    assert status["tts"] == {
        "provider": "groq",
        "model": "canopylabs/orpheus-v1-english",
        "fallback": [],
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
    runtime._audio_pool = __import__("jenefar.core.provider_pool", fromlist=["ProviderPool"]).ProviderPool()
    line = runtime.provider_status_line()
    assert "STT=groq/whisper-large-v3 fallback=none" in line
    assert "TTS=groq/canopylabs/orpheus-v1-english fallback=none" in line


def test_voice_reports_separate_stt_and_tts_capabilities(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    monkeypatch.setenv("JENEFAR_VOICE_PROVIDER_ORDER", "openai,groq")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"]["provider"] == "openai"
    assert status["tts"]["provider"] == "openai"
    assert status["tts"]["fallback"] == ["groq"]


def test_groq_can_be_disabled_for_tts_when_terms_are_not_accepted(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    monkeypatch.setenv("JENEFAR_DISABLE_GROQ_TTS", "1")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"]["provider"] == "groq"
    assert status["tts"] is None


def test_default_runtime_desktop_status_is_wired():
    from pathlib import Path

    source = Path("run.py").read_text(encoding="utf-8")
    assert "desktop_status = orchestrator.tool_broker.desktop.backend_status()" in source


def test_default_runtime_starts_avatar_server():
    from pathlib import Path

    source = Path("run.py").read_text(encoding="utf-8")
    assert "AvatarController()" in source
    assert "AvatarServer(" in source
    assert "webbrowser.open(runtime_url)" in source
    assert "BrowserVoiceBridge(orchestrator, avatar=avatar)" in source


def test_run_py_default_uses_browser_voice_runtime():
    from pathlib import Path

    source = Path("run.py").read_text(encoding="utf-8")
    assert "BrowserVoiceBridge(orchestrator, avatar=avatar)" in source
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
    from jenefar.core.provider_pool import ProviderPool

    runtime._audio_pool = ProviderPool()
    pcm = b"\x00\x00" * 16000
    result = asyncio.run(runtime._transcribe_groq(runtime._wav_bytes(pcm)))
    assert result == "Hello Jenefar"
    assert captured["model"] == "whisper-large-v3"
    assert captured["language"] == "hi"
    assert captured["temperature"] == 0.0
    assert "prompt" not in captured


def test_stt_falls_back_from_openai_quota_to_groq(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    monkeypatch.setenv("JENEFAR_VOICE_PROVIDER_ORDER", "openai,groq")
    runtime = ProviderVoiceRuntime.__new__(ProviderVoiceRuntime)
    from jenefar.core.provider_pool import ProviderPool

    runtime._audio_pool = ProviderPool()
    calls = []

    async def fail_openai(_audio):
        calls.append("openai")
        error = RuntimeError("429 insufficient_quota credit_balance_exhausted")
        error.status_code = 429
        raise error

    async def succeed_groq(_audio):
        calls.append("groq")
        return "hello jenefar"

    monkeypatch.setattr(ProviderVoiceRuntime, "_transcribe_openai", staticmethod(fail_openai))
    monkeypatch.setattr(ProviderVoiceRuntime, "_transcribe_groq", staticmethod(succeed_groq))

    result = asyncio.run(runtime.transcribe_pcm(b"\x00\x00" * 16000))
    assert result == "hello jenefar"
    assert calls == ["openai", "groq"]
    assert not runtime._audio_pool.available("openai")


def test_tts_falls_back_from_openai_quota_to_groq(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    monkeypatch.setenv("JENEFAR_VOICE_PROVIDER_ORDER", "openai,groq")
    runtime = ProviderVoiceRuntime.__new__(ProviderVoiceRuntime)
    from jenefar.core.provider_pool import ProviderPool

    runtime._audio_pool = ProviderPool()
    calls = []

    async def fail_openai(_self, _text):
        calls.append("openai")
        error = RuntimeError("429 credit_balance_exhausted")
        error.status_code = 429
        raise error

    async def succeed_groq(_self, _text):
        calls.append("groq")

    monkeypatch.setattr(ProviderVoiceRuntime, "_speak_openai", fail_openai)
    monkeypatch.setattr(ProviderVoiceRuntime, "_speak_groq", succeed_groq)

    asyncio.run(runtime.speak("hello"))
    assert calls == ["openai", "groq"]
    assert not runtime._audio_pool.available("openai")


def test_quota_failure_gets_long_cooldown(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    runtime = ProviderVoiceRuntime.__new__(ProviderVoiceRuntime)
    from jenefar.core.provider_pool import ProviderPool

    runtime._audio_pool = ProviderPool()
    runtime._mark_failed_provider("openai", RuntimeError("insufficient_quota"))
    remaining = runtime._audio_pool.cooldowns["openai"] - __import__("time").monotonic()
    assert remaining > 3000


def test_wakeword_normalizes_common_jennifer_variant():
    from jenefar.voice.wakeword import WakeWord

    wake = WakeWord(["Hi Jenefar", "Hello Jenefar"])
    assert wake.matched_phrase("Hello Jennifer") == "hello jenefar"
    assert wake.remove_wake_phrase("Hello Jennifer") == ""


def test_hinglish_stt_defaults_to_hindi(monkeypatch):
    monkeypatch.delenv("GROQ_STT_LANGUAGE", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")
    assert __import__("os").getenv("GROQ_STT_LANGUAGE") is None


def test_workspace_root_request_maps_to_primary_root(tmp_path, monkeypatch):
    from jenefar.workspace.policy import WorkspacePolicy
    policy = WorkspacePolicy(roots=[str(tmp_path)])
    assert policy.require_allowed("/") == tmp_path


def test_llm_client_has_repeated_tool_loop_guard():
    from jenefar.core.llm import LLMClient
    result = LLMClient._repeated_tool_response(
        "openrouter", "resp", "model", "role"
    )
    assert result.provider == "openrouter"
    assert "repeated tool loop" in result.text.lower()
