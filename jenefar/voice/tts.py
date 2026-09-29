from __future__ import annotations
from typing import Protocol

class TextToSpeech(Protocol):
    def speak(self, text: str) -> None: ...

class ConsoleTTS:
    def speak(self, text: str) -> None:
        print(f"Jenefar > {text}")
