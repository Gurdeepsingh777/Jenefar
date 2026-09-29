from __future__ import annotations
from dataclasses import dataclass

from jenefar.voice.backend import VoiceBackend, VoiceEvent

@dataclass
class VoicePipeline:
    backend: VoiceBackend

    def next_event(self) -> VoiceEvent | None:
        return self.backend.listen()
