from __future__ import annotations
from typing import Protocol

class SpeechToText(Protocol):
    def transcribe(self, audio: bytes) -> str: ...

class TextInputSTT:
    """Development STT adapter; real microphone STT plugs into the same interface."""
    def transcribe(self, audio: bytes) -> str:
        return audio.decode("utf-8", errors="ignore").strip()
