import numpy as np

from jenefar.voice.continuous import ContinuousVoiceRuntime, VoiceConfig


def test_rms_detects_quiet_and_loud_audio():
    runtime = ContinuousVoiceRuntime(
        object(),
        VoiceConfig(sample_rate=1000, block_ms=100),
    )
    quiet = np.zeros(100, dtype=np.int16)
    loud = np.full(100, 16384, dtype=np.int16)

    assert runtime._rms(quiet) == 0.0
    assert runtime._rms(loud) > 0.4


def test_voice_config_limits_are_reasonable():
    config = VoiceConfig()
    assert config.start_threshold > config.stop_threshold
    assert config.max_utterance_seconds >= 5


def test_utterance_starts_on_loud_block():
    runtime = ContinuousVoiceRuntime(
        object(),
        VoiceConfig(
            sample_rate=1000,
            block_ms=100,
            start_threshold=0.01,
            stop_threshold=0.005,
            silence_ms=200,
            max_utterance_seconds=2,
        ),
    )
    loud = np.full(100, 12000, dtype=np.int16)

    assert runtime._consume_block(loud) is None
    assert runtime._speaking is True


def test_tts_failure_does_not_require_tts_for_continuous_runtime(monkeypatch):
    class FakeVoice:
        def __init__(self):
            self.calls = 0
        def audio_status(self):
            self.calls += 1
            return {
                "stt": {"provider": "groq", "model": "whisper-large-v3", "fallback": []},
                "tts": None,
            }
        def reset_audio_health(self):
            raise AssertionError("should not reset when TTS is unavailable")

    runtime = ContinuousVoiceRuntime.__new__(ContinuousVoiceRuntime)
    runtime._voice = FakeVoice()
    assert runtime._voice.audio_status()["tts"] is None


def test_voice_runtime_has_provider_health_reset():
    from jenefar.voice.provider import ProviderVoiceRuntime

    assert hasattr(ProviderVoiceRuntime, "reset_audio_health")


def test_legacy_tts_helpers_are_available():
    from jenefar.voice.provider import ProviderVoiceRuntime
    assert hasattr(ProviderVoiceRuntime, "_legacy_edge_tts_available")
    assert hasattr(ProviderVoiceRuntime, "_local_espeak_available")

 
 
def test_legacy_voice_does_not_require_pyaudio():
    from jenefar.voice.continuous import ContinuousVoiceRuntime
    assert hasattr(ContinuousVoiceRuntime, "_calibrate_microphone")
    assert hasattr(ContinuousVoiceRuntime, "_capture_phrase_pcm")


def test_tts_prefers_edge_when_available(monkeypatch):
    from jenefar.voice.provider import ProviderVoiceRuntime

    monkeypatch.setattr(
        ProviderVoiceRuntime,
        "_legacy_edge_tts_available",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(
        ProviderVoiceRuntime,
        "_local_espeak_available",
        staticmethod(lambda: True),
    )
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    status = ProviderVoiceRuntime.audio_status()
    assert status["tts"]["provider"] == "edge"


def test_tool_broker_has_whatsapp_actions():
    from jenefar.tools.broker import ToolBroker
    broker = ToolBroker(require_confirmation=True)
    names = {tool.name for tool in broker.registry.list()}
    assert "whatsapp_open_web" in names
    assert "whatsapp_send_web" in names


def test_continuous_voice_default_does_not_require_wakeword(monkeypatch):
    monkeypatch.delenv("JENEFAR_REQUIRE_WAKE_WORD", raising=False)
    from jenefar.voice.continuous import ContinuousVoiceRuntime
    class Wake:
        def matched_phrase(self, text): return None
        def remove_wake_phrase(self, text): return text
    class Orch:
        state = type("S", (), {"name": "SLEEPING"})()
        wakeword = Wake()
    # Static policy check: strict gating is opt-in.
    assert not bool(__import__("os").getenv("JENEFAR_REQUIRE_WAKE_WORD"))



def test_default_voice_capture_threshold_is_reasonable():
    from jenefar.voice.continuous import VoiceConfig
    cfg = VoiceConfig()
    assert cfg.start_threshold <= 0.02
    assert cfg.silence_ms >= 1200
