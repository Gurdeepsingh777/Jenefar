from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Expression:
    name: str
    intensity: float = 0.0


class ExpressionEngine:
    """Deterministic local expression mapper for the avatar runtime."""

    _RULES = (
        ("alert", ("error", "warning", "blocked", "failed", "danger", "security"), 0.9),
        ("happy", ("great", "done", "success", "completed", "welcome", "thanks"), 0.7),
        ("curious", ("why", "how", "what", "which", "explain", "research"), 0.55),
        ("focused", ("analyzing", "processing", "thinking", "testing", "debugging"), 0.65),
    )

    def classify(self, state: str, text: str = "") -> Expression:
        lowered = text.lower()

        if state == "thinking":
            return Expression("focused", 0.7)
        if state == "waiting_approval":
            return Expression("alert", 0.75)
        if state == "listening":
            return Expression("curious", 0.45)
        if state == "speaking":
            for name, keywords, intensity in self._RULES:
                if any(keyword in lowered for keyword in keywords):
                    return Expression(name, intensity)
            return Expression("neutral", 0.35)

        for name, keywords, intensity in self._RULES:
            if any(keyword in lowered for keyword in keywords):
                return Expression(name, intensity)

        return Expression("neutral", 0.0)
