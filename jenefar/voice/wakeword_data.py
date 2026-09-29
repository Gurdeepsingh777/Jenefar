from __future__ import annotations

import os
from pathlib import Path

import numpy as np


def _iter_audio_files(root: Path):
    extensions = {".wav", ".flac", ".ogg", ".mp3"}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in extensions:
            yield path


def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf
    except Exception as exc:
        raise RuntimeError(
            "soundfile is required for wake-word validation feature preparation. "
            "Install requirements-optional.txt."
        ) from exc
    data, sample_rate = sf.read(str(path), dtype="int16", always_2d=False)
    data = np.asarray(data)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.int16), int(sample_rate)


def _resample(audio: np.ndarray, sample_rate: int, target_rate: int = 16000) -> np.ndarray:
    if sample_rate == target_rate:
        return audio.astype(np.int16, copy=False)
    if audio.size == 0:
        return np.zeros(0, dtype=np.int16)
    target_len = max(1, int(round(audio.size * target_rate / sample_rate)))
    x_old = np.linspace(0.0, 1.0, audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, target_len, endpoint=False)
    return np.clip(np.interp(x_new, x_old, audio), -32768, 32767).astype(np.int16)


def prepare_validation_features(
    audio_root: str | Path,
    output_file: str | Path,
    *,
    hours: float = 11.3,
    batch_size: int = 32,
) -> Path:
    if hours <= 0:
        raise ValueError("hours must be positive")
    root = Path(audio_root)
    if not root.exists():
        raise FileNotFoundError(root)

    try:
        from openwakeword.utils import AudioFeatures
    except Exception as exc:
        raise RuntimeError(
            "openwakeword with its feature models must be installed before preparing "
            "validation features."
        ) from exc

    audio_files = list(_iter_audio_files(root))
    if not audio_files:
        raise RuntimeError(f"No audio files found under {root}")

    target_samples = int(hours * 3600 * 16000)
    clip_samples = 51200
    extractor = AudioFeatures(
        sr=16000,
        ncpu=max(1, (os.cpu_count() or 2) // 2),
        inference_framework="onnx",
        device="cpu",
    )

    features: list[np.ndarray] = []
    consumed = 0
    batch: list[np.ndarray] = []

    def flush() -> None:
        if not batch:
            return
        clips = np.stack(batch)
        embedded = extractor.embed_clips(
            clips,
            batch_size=min(batch_size, len(batch)),
            ncpu=max(1, (os.cpu_count() or 2) // 2),
        )
        features.append(embedded.reshape(-1, embedded.shape[-1]).astype(np.float32))
        batch.clear()

    for path in audio_files:
        if consumed >= target_samples:
            break
        try:
            audio, rate = _load_audio(path)
            audio = _resample(audio, rate)
        except Exception:
            continue
        if audio.size == 0:
            continue
        offset = 0
        while offset < audio.size and consumed < target_samples:
            remaining = min(clip_samples, audio.size - offset, target_samples - consumed)
            clip = audio[offset:offset + remaining]
            if clip.size < clip_samples:
                padded = np.zeros(clip_samples, dtype=np.int16)
                padded[:clip.size] = clip
                clip = padded
            batch.append(clip)
            offset += int(remaining)
            consumed += int(remaining)
            if len(batch) >= batch_size:
                flush()

    rng = np.random.default_rng(20260930)
    while consumed < target_samples:
        remaining = min(clip_samples, target_samples - consumed)
        clip = rng.normal(0.0, 300.0, clip_samples).clip(-32768, 32767).astype(np.int16)
        if remaining < clip_samples:
            clip[remaining:] = 0
        batch.append(clip)
        consumed += int(remaining)
        if len(batch) >= batch_size:
            flush()

    flush()
    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.save(output, np.vstack(features))
    return output
