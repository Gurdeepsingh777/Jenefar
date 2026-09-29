from __future__ import annotations

import os

import numpy as np


class WakeWordEngine:
    """Optional low-latency local wake-word detector using openWakeWord."""

    def __init__(self, model_path: str | None = None, threshold: float | None = None):
        self.model_path = model_path or os.getenv("JENEFAR_WAKEWORD_MODEL_PATH", "").strip()
        self.threshold = float(
            threshold if threshold is not None
            else os.getenv("JENEFAR_WAKEWORD_THRESHOLD", "0.55")
        )
        self.model = None
        self.available = False
        self._prediction_key = ""

        if self.model_path:
            try:
                from openwakeword.model import Model
                self.model = Model(wakeword_models=[self.model_path])
                self.available = True
                self._prediction_key = next(iter(self.model.prediction_buffer.keys()), "")
            except Exception:
                self.model = None
                self.available = False

    @staticmethod
    def _to_mono_16k(audio: np.ndarray, sample_rate: int) -> np.ndarray:
        data = np.asarray(audio)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data.astype(np.float32)
        if sample_rate == 16000:
            return data.astype(np.int16)

        output_size = max(1, int(len(data) * 16000 / sample_rate))
        if len(data) == 0:
            return np.zeros(output_size, dtype=np.int16)

        x_old = np.linspace(0.0, 1.0, len(data), endpoint=False)
        x_new = np.linspace(0.0, 1.0, output_size, endpoint=False)
        resampled = np.interp(x_new, x_old, data)
        return np.clip(resampled, -32768, 32767).astype(np.int16)

    def process(self, audio: np.ndarray, *, sample_rate: int) -> tuple[bool, float]:
        if not self.available or self.model is None:
            return False, 0.0

        frame = self._to_mono_16k(audio, sample_rate)
        if frame.size == 0:
            return False, 0.0

        try:
            predictions = self.model.predict(frame)
        except Exception:
            return False, 0.0

        if isinstance(predictions, dict):
            if self._prediction_key:
                score = float(predictions.get(self._prediction_key, 0.0))
            else:
                score = max((float(v) for v in predictions.values()), default=0.0)
        else:
            score = float(predictions)

        return score >= self.threshold, score

    @classmethod
    def from_environment(cls) -> "WakeWordEngine":
        return cls()
