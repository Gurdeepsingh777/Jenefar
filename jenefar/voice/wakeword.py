from __future__ import annotations


class WakeWord:
    def __init__(self, phrases: list[str]) -> None:
        self.phrases = [
            " ".join(phrase.lower().split())
            for phrase in phrases
            if phrase.strip()
        ]

    def detect(self, text: str) -> bool:
        normalized = " ".join(text.lower().strip().split())
        return any(
            normalized == phrase or normalized.startswith(phrase + " ")
            for phrase in self.phrases
        )

    def remove_wake_phrase(self, text: str) -> str:
        original = text.strip()
        normalized = " ".join(original.lower().split())

        for phrase in sorted(self.phrases, key=len, reverse=True):
            if normalized == phrase:
                return ""

            prefix = phrase + " "
            if normalized.startswith(prefix):
                # Determine removal against normalized text. This intentionally
                # returns a normalized remainder for predictable routing.
                return normalized[len(prefix):].strip()

        return original
