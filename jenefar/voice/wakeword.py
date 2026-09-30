from __future__ import annotations


class WakeWord:
    def __init__(self, phrases: list[str]) -> None:
        self.phrases = [
            " ".join(phrase.lower().split())
            for phrase in phrases
            if phrase.strip()
        ]

    @staticmethod
    def normalize_stt_text(text: str) -> str:
        normalized = " ".join(text.lower().strip().split())
        for source, target in {
            "jennifer": "jenefar",
            "jenifer": "jenefar",
            "jennifer.": "jenefar",
            "jennifer!": "jenefar",
            "jennifer?": "jenefar",
            "jeneferr": "jenefar",
        }.items():
            normalized = normalized.replace(source, target)
        return normalized

    def matched_phrase(self, text: str) -> str | None:
        normalized = self.normalize_stt_text(text)
    def detect(self, text: str) -> bool:
        return self.matched_phrase(text) is not None

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
