from __future__ import annotations

import re


class WakeWord:
    def __init__(self, phrases: list[str]) -> None:
        self.phrases = [
            " ".join(phrase.lower().split())
            for phrase in phrases
            if phrase.strip()
        ]

    @staticmethod
    def normalize_stt_text(text: str) -> str:
        normalized = " ".join(str(text or "").lower().strip().split())
        for source, target in {
            "jennifer": "jenefar",
            "jenifer": "jenefar",
            "jeneferr": "jenefar",
        }.items():
            normalized = normalized.replace(source, target)
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        return " ".join(normalized.split())

    def matched_phrase(self, text: str) -> str | None:
        normalized = self.normalize_stt_text(text)
        for phrase in sorted(self.phrases, key=len, reverse=True):
            if normalized == phrase or normalized.startswith(phrase + " "):
                return phrase
        return None

    def detect(self, text: str) -> bool:
        return self.matched_phrase(text) is not None

    def remove_wake_phrase(self, text: str) -> str:
        original = str(text or "").strip()
        phrase = self.matched_phrase(original)
        if phrase is None:
            return original
        match = re.match(self._wake_prefix_pattern(phrase), original, re.IGNORECASE)
        if match:
            return original[match.end():].strip().lower()
        normalized = self.normalize_stt_text(original)
        if normalized == phrase:
            return ""
        return normalized[len(phrase):].strip()

    @staticmethod
    def _wake_prefix_pattern(phrase: str) -> str:
        parts = []
        for token in phrase.split():
            if token == "jenefar":
                parts.append(r"(?:jenefar|jennifer|jenifer|jeneferr)")
            else:
                parts.append(re.escape(token))
        separator = r"[\s,.:;!?\"'`~_\-]+"
        return r"^(?:" + separator + r")*" + separator.join(parts) + r"(?:" + separator + r")*"
