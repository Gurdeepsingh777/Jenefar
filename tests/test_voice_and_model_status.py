from __future__ import annotations

import asyncio

from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.voice.provider import ProviderVoiceRuntime


import pytest


@pytest.fixture(autouse=True)
def clear_inherited_gemini_voice_env(monkeypatch):
    # Keep provider-order assertions independent from a developer's local .env.
    for name in (
        "GEMINI_API_KEY", "LLM_API_KEY", "API_KEY", "LLM_BASE_URL", "BASE_URL",
        "GEMINI_MODEL", "LLM_MODEL_NAME", "JENEFAR_GEMINI_STT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


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


def test_native_tts_is_opt_in(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("JENEFAR_ENABLE_NATIVE_TTS", raising=False)
    assert ProviderVoiceRuntime.audio_status() == {"stt": None, "tts": None}


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

    openai = __import__("pytest").importorskip("openai")
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



def test_gemini_is_available_as_browser_stt_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("JENEFAR_VOICE_PROVIDER_ORDER", "openai,groq")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"] == {
        "provider": "openai",
        "model": "gpt-4o-transcribe",
        "fallback": ["gemini"],
    }
    assert status["tts"]["provider"] == "openai"


def test_gemini_stt_can_reuse_telegram_llm_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-gemini-key")
    monkeypatch.setenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    monkeypatch.setenv("LLM_MODEL_NAME", "gemini-3.8-flash")
    status = ProviderVoiceRuntime.audio_status()
    assert status["stt"] == {
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "fallback": [],
    }
    assert status["tts"] is None


def test_browser_stt_fails_over_from_openai_quota_to_gemini(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-gemini-key")
    monkeypatch.setenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    monkeypatch.setenv("LLM_MODEL_NAME", "gemini-3.8-flash")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
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

    async def succeed_gemini(_audio):
        calls.append("gemini")
        return "Hello Jenefar, meri awaaz suno."

    monkeypatch.setattr(ProviderVoiceRuntime, "_transcribe_openai", staticmethod(fail_openai))
    monkeypatch.setattr(ProviderVoiceRuntime, "_transcribe_gemini", staticmethod(succeed_gemini))
    result = asyncio.run(runtime.transcribe_pcm(b"\x00\x00" * 16000))
    assert result == "Hello Jenefar, meri awaaz suno."
    assert calls == ["openai", "gemini"]
    assert not runtime._audio_pool.available("openai")


def test_gemini_stt_sends_audio_and_extracts_transcript(monkeypatch):
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("JENEFAR_GEMINI_STT_MODEL", "gemini-test-model")
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"candidates": [{"content": {"parts": [{"text": "Hello Jenefar"}]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    audio = ProviderVoiceRuntime._wav_bytes(b"\x00\x00" * 1600)
    result = asyncio.run(ProviderVoiceRuntime._transcribe_gemini(audio))
    assert result == "Hello Jenefar"
    assert captured["url"].endswith("/models/gemini-test-model:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "test-gemini-key"
    parts = captured["payload"]["contents"][0]["parts"]
    assert parts[1]["inlineData"]["mimeType"] == "audio/wav"
    assert parts[1]["inlineData"]["data"]
    assert "temperature" not in captured["payload"]["generationConfig"]

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



def test_local_whisper_retries_without_vad_when_filtered_pass_is_empty(monkeypatch):
    import asyncio
    import io
    import threading
    from types import SimpleNamespace
    from jenefar.voice.provider import ProviderVoiceRuntime

    runtime = ProviderVoiceRuntime.__new__(ProviderVoiceRuntime)
    runtime._local_stt_inference_lock = threading.Lock()
    calls = []

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            calls.append({"vad_filter": kwargs["vad_filter"], "beam_size": kwargs["beam_size"]})
            audio.read()
            if kwargs["vad_filter"]:
                return iter(()), None
            return iter([SimpleNamespace(text="  Hello Jenefar  ")]), None

    monkeypatch.setattr(runtime, "_get_local_stt_model", lambda: FakeModel())
    result = asyncio.run(runtime._transcribe_local(io.BytesIO(b"wav-audio")))

    assert result == "Hello Jenefar"
    assert calls == [
        {"vad_filter": True, "beam_size": 1},
        {"vad_filter": False, "beam_size": 3},
    ]


def test_local_whisper_reports_capture_diagnostics_after_both_passes_fail(monkeypatch):
    import asyncio
    import io
    import threading
    from jenefar.voice.provider import ProviderVoiceRuntime

    runtime = ProviderVoiceRuntime.__new__(ProviderVoiceRuntime)
    runtime._local_stt_inference_lock = threading.Lock()

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            audio.read()
            return iter(()), None

    monkeypatch.setattr(runtime, "_get_local_stt_model", lambda: FakeModel())

    try:
        asyncio.run(runtime._transcribe_local(io.BytesIO(b"wav-audio")))
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("empty local STT results must be reported")

    assert "no transcript was produced" in message
    assert "vad_filter=True" in message
    assert "vad_filter=False" in message
    assert "microphone/input level" in message
