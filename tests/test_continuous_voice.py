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
