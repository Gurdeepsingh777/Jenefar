from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class VoiceEvent:
    text: str
    source: str = "text"


class VoiceBackend:
    """Pluggable voice backend. Real microphone/STT/TTS adapters can implement this."""

    def __init__(self, on_text: Optional[Callable[[VoiceEvent], None]] = None) -> None:
        self.on_text = on_text

    def start(self) -> None:
        raise NotImplementedError("No voice backend configured.")

    def stop(self) -> None:
        pass

    def speak(self, text: str) -> None:
        raise NotImplementedError("No TTS backend configured.")
