from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

Complexity = Literal["simple", "standard", "hard"]

SIMPLE_MARKERS = (
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay",
    "what time", "current time", "date today", "today's date",
    "kya time", "kitna baja", "good morning", "good night",
)
HARD_MARKERS = (
    "debug", "implement", "multi-file", "multiple files", "across files",
    "refactor", "architecture", "self-heal", "kali", "nmap", "exploit",
    "bug bounty", "plan then", "then test", "then report", "compound",
    "diagnose", "fix then", "end to end", "end-to-end",
)
STANDARD_MARKERS = (
    "edit", "fix", "add a", "docstring", "single file", ".py",
    "search", "fetch", "open", "click",
)
HARD_AGENTS = {
    "kali", "cybersecurity", "bugbounty", "gui_vision", "robotics",
}
BUDGETS = {
    "simple": 4,
    "standard": 8,
    "hard": 16,
}


@dataclass(frozen=True)
class ComplexityResult:
    level: Complexity
    source: str
    reason: str


class ComplexityClassifier:
    """Heuristic-first complexity classifier with optional fast-model fallback."""

    def __init__(self, llm_complete: Callable[[str], str] | None = None) -> None:
        self.llm_complete = llm_complete

    def classify(self, text: str, plan: Any | None = None) -> ComplexityResult:
        try:
            return self._classify(text, plan)
        except Exception:
            return ComplexityResult("standard", "fallback", "classifier error")

    def _classify(self, text: str, plan: Any | None) -> ComplexityResult:
        lowered = " ".join(str(text or "").lower().split())
        agent = str(getattr(plan, "agent", "") or "").strip().lower()
        needs_tool = bool(getattr(plan, "needs_tool", False))
        is_compound = bool(getattr(plan, "is_compound", False))
        confidence = float(getattr(plan, "confidence", 0.5) or 0.5)

        if self._is_simple(lowered, agent, needs_tool):
            return ComplexityResult("simple", "heuristic", "short greeting or lookup")
        if is_compound or agent in HARD_AGENTS:
            return ComplexityResult("hard", "heuristic", "compound or high-impact specialist")
        if _contains_marker(lowered, HARD_MARKERS):
            return ComplexityResult("hard", "heuristic", "hard keyword match")
        if len(lowered.split()) >= 28:
            return ComplexityResult("hard", "heuristic", "long multi-step request")

        if _contains_marker(lowered, STANDARD_MARKERS) or needs_tool:
            return ComplexityResult("standard", "heuristic", "single-tool or file task")

        if confidence < 0.75 or agent in {"research", ""}:
            llm_result = self._llm_classify(text)
            if llm_result is not None:
                return llm_result
            return ComplexityResult("standard", "heuristic", "uncertain fallback")

        return ComplexityResult("standard", "heuristic", "default")

    @staticmethod
    def _is_simple(lowered: str, agent: str, needs_tool: bool) -> bool:
        words = lowered.split()
        if not words:
            return True
        if len(words) <= 3:
            return True
        if agent == "utility" and len(words) <= 12:
            return True
        if _contains_marker(lowered, SIMPLE_MARKERS) and len(words) <= 10:
            return True
        return False

    def _llm_classify(self, text: str) -> ComplexityResult | None:
        if self.llm_complete is None:
            return None
        prompt = (
            "Classify the user request complexity as simple, standard, or hard. "
            "Reply with JSON only: {\"level\": \"simple|standard|hard\", \"reason\": \"...\"}.\n"
            f"Request: {text}"
        )
        raw = self.llm_complete(prompt)
        payload = _parse_json_object(raw)
        level = str(payload.get("level", "")).strip().lower()
        if level not in {"simple", "standard", "hard"}:
            return None
        reason = str(payload.get("reason") or "llm classification")
        return ComplexityResult(level, "llm", reason)  # type: ignore[arg-type]


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    for marker in markers:
        token = marker.strip().lower()
        if not token:
            continue
        if " " in token:
            if token in text:
                return True
            continue
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text):
            return True
    return False


def tool_round_budget(complexity: str, agent_max: int = 4) -> int:
    base = BUDGETS.get(str(complexity or "").strip().lower(), BUDGETS["standard"])
    capped = min(max(int(agent_max), base), 20)
    if int(agent_max) >= 20:
        return 20
    return min(20, max(base, int(agent_max)))


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


__all__ = [
    "Complexity",
    "ComplexityResult",
    "ComplexityClassifier",
    "tool_round_budget",
]
