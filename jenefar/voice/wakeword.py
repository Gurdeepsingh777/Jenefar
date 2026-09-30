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
        for phrase in sorted(self.phrases, key=len, reverse=True):
            if normalized == phrase or normalized.startswith(phrase + " "):
                return phrase
        return None

    def detect(self, text: str) -> bool:
        return self.matched_phrase(text) is not None

    def remove_wake_phrase(self, text: str) -> str:
        normalized = self.normalize_stt_text(text)

        for phrase in sorted(self.phrases, key=len, reverse=True):
            if normalized == phrase:
                return ""

            prefix = phrase + " "
            if normalized.startswith(prefix):
                return normalized[len(prefix):].strip()

        return text.strip()
