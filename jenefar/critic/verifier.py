from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CLAIM_MARKERS = (
    "i updated", "i edited", "i changed", "i created", "i ran",
    "tests passed", "file ran successfully", "successfully ran",
    "screenshot", "on your screen", "screen par", "fetched",
    "downloaded", "i opened",
)
FILE_MARKERS = (".py", ".md", ".json", ".txt", "file", "workspace")
SCREEN_MARKERS = ("screen", "screenshot", "desktop", "gui")
WEB_MARKERS = ("http://", "https://", "web search", "fetched url", "github")


@dataclass(frozen=True)
class Critique:
    passed: bool
    notes: str
    skipped: bool = False
    source: str = "checklist"


class Verifier:
    """Checklist critic with optional LLM hook. Never raises to the orchestrator."""

    def __init__(self, llm_complete=None) -> None:
        self.llm_complete = llm_complete

    def review(
        self,
        task: str,
        result: str,
        *,
        complexity: str = "standard",
        tool_trace: list[dict[str, Any]] | None = None,
    ) -> Critique:
        try:
            return self._review(task, result, complexity=complexity, tool_trace=tool_trace)
        except Exception as exc:
            return Critique(True, f"critic skipped: {type(exc).__name__}", skipped=True, source="error")

    def verify(
        self,
        task: str,
        result: str,
        *,
        complexity: str = "standard",
        tool_trace: list[dict[str, Any]] | None = None,
        critic_pass: int = 0,
    ) -> str:
        try:
            text = str(result or "")
            if not text.strip():
                return "No usable result was produced."
            critique = self.review(
                task,
                text,
                complexity=complexity,
                tool_trace=tool_trace,
            )
            if critique.skipped or critique.passed:
                return text
            if int(critic_pass) >= 1:
                return text.rstrip() + " I could not verify this result."
            return text
        except Exception:
            return str(result or "") or "No usable result was produced."

    def _review(
        self,
        task: str,
        result: str,
        *,
        complexity: str,
        tool_trace: list[dict[str, Any]] | None,
    ) -> Critique:
        if str(complexity or "").strip().lower() == "simple":
            return Critique(True, "simple task skipped", skipped=True)

        text = str(result or "")
        if not text.strip():
            return Critique(False, "empty result")

        lowered = text.lower()
        tools = list(tool_trace or [])
        tool_names = {str(item.get("name", "")).lower() for item in tools}
        tool_error = any(str(item.get("status", "")).lower() == "error" for item in tools)

        if tool_error and not any(token in lowered for token in ("error", "fail", "could not", "unable")):
            return Critique(False, "ignored tool error")

        claimed = any(marker in lowered for marker in CLAIM_MARKERS)
        if claimed and not tools:
            if any(marker in lowered or marker in task.lower() for marker in FILE_MARKERS + SCREEN_MARKERS + WEB_MARKERS):
                return Critique(False, "claimed file/screen/web result without tool output")

        if self.llm_complete is not None:
            llm_critique = self._llm_review(task, text, tools)
            if llm_critique is not None:
                return llm_critique
        return Critique(True, "checklist passed")

    def _llm_review(self, task: str, result: str, tools: list[dict[str, Any]]) -> Critique | None:
        prompt = (
            "Review whether the assistant finished the user task honestly. "
            "Reply JSON only: {\"passed\": true|false, \"notes\": \"...\"}.\n"
            f"Task: {task}\nResult: {result}\nTools: {tools}"
        )
        raw = str(self.llm_complete(prompt) or "")
        lowered = raw.lower()
        if '"passed": false' in lowered or '"passed":false' in lowered:
            return Critique(False, raw, source="llm")
        if '"passed": true' in lowered or '"passed":true' in lowered:
            return Critique(True, raw, source="llm")
        return None


__all__ = ["Critique", "Verifier"]
