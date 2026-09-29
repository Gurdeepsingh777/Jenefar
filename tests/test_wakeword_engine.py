import numpy as np

from jenefar.voice.wakeword_engine import WakeWordEngine


def test_wakeword_engine_without_model_is_inactive(monkeypatch):
    monkeypatch.delenv("JENEFAR_WAKEWORD_MODEL_PATH", raising=False)
    engine = WakeWordEngine.from_environment()
    detected, score = engine.process(np.zeros(1600, dtype=np.int16), sample_rate=16000)
    assert detected is False
    assert score == 0.0
