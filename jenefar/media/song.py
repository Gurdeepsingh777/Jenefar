from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path


async def _recognize(path: str) -> dict[str, object]:
    try:
        from shazamio import Serialize, Shazam
    except ImportError as exc:
        raise RuntimeError("Song recognition requires optional package 'shazamio'.") from exc

    async with Shazam() as shazam:
        result = await shazam.recognize(path)

    track = Serialize.full_track(result).track
    return {
        "title": str(getattr(track, "title", "") or ""),
        "artist": str(getattr(track, "subtitle", "") or ""),
        "url": str(getattr(track, "url", "") or ""),
    }


def recognize_audio_file(path: str) -> dict[str, object]:
    return asyncio.run(_recognize(path))


def record_and_recognize(seconds: int = 10, sample_rate: int = 44100) -> dict[str, object]:
    try:
        import sounddevice as sd
        import soundfile as sf
        import numpy as np  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Microphone song recognition requires sounddevice, soundfile and numpy."
        ) from exc

    seconds = max(4, min(int(seconds), 20))
    print("[JENEFAR] Listening to the song...")
    audio = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
    )
    sd.wait()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        temp_path = Path(handle.name)

    try:
        sf.write(str(temp_path), audio, sample_rate, subtype="PCM_16")
        return recognize_audio_file(str(temp_path))
    finally:
        temp_path.unlink(missing_ok=True)
