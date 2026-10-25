from __future__ import annotations

import json
import re
from typing import Any, Callable

from jenefar.core.planner import Plan

ALLOWED_AGENTS = frozenset({
    "repository",
    "local_development",
    "gui_vision",
    "automation",
    "kali",
    "python",
    "cybersecurity",
    "bugbounty",
    "robotics",
    "utility",
    "research",
})


class LLMIntentFallback:
    """Refine a low-confidence keyword plan with a fast-model JSON intent."""

    def __init__(
        self,
        llm_complete: Callable[[str], str] | None = None,
        threshold: float = 0.75,
    ) -> None:
        self.llm_complete = llm_complete
        self.threshold = threshold

    def refine(self, text: str, plan: Plan) -> Plan:
        try:
            if float(plan.confidence) >= self.threshold:
                return plan
            if self.llm_complete is None:
                return plan
            prompt = (
                "Choose the best Jenefar specialist for this request. "
                "Reply with JSON only: "
                '{"intent": str, "agent": str, "needs_tool": bool, "reason": str}. '
                f"Allowed agents: {', '.join(sorted(ALLOWED_AGENTS))}.\n"
                f"Request: {text}\n"
                f"Keyword plan: intent={plan.intent} agent={plan.agent} "
                f"confidence={plan.confidence} reason={plan.reason}"
            )
            payload = _parse_json_object(self.llm_complete(prompt))
            agent = str(payload.get("agent") or "").strip()
            if agent not in ALLOWED_AGENTS:
                return plan
            intent = str(payload.get("intent") or agent).strip() or agent
            needs_tool = bool(payload.get("needs_tool"))
            reason = str(payload.get("reason") or "llm intent fallback").strip()
            return Plan(
                intent=intent,
                agent=agent,
                needs_tool=needs_tool,
                confidence=max(self.threshold, 0.8),
                reason=f"llm-fallback: {reason}",
                steps=list(plan.steps),
            )
        except Exception:
            return plan


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


__all__ = ["ALLOWED_AGENTS", "LLMIntentFallback"]
