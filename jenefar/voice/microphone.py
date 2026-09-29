from __future__ import annotations
import sys

class Microphone:
    """Minimal input backend. Voice providers can replace this adapter."""
    def listen(self, prompt: str = "You > ") -> str:
        return input(prompt).strip()
