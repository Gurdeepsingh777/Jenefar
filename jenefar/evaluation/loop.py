from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from pathlib import Path
import threading
from typing import Any

from jenefar.evaluation.trace import redact_sensitive


@dataclass(frozen=True)
class EvaluationResult:
    score: float
    passed: bool
    reasons: tuple[str, ...]


class EvaluationLoop:
    """Runtime quality evaluation and structured learning-signal collection."""

    _append_lock = threading.Lock()

    def __init__(self, path: str | Path = "data/evaluations.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def evaluate(
        self,
        task: str,
        result: str,
        provider: str = "",
        *,
        trace: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        reasons: list[str] = []
        score = 1.0
        if not result.strip():
            score -= 0.7
            reasons.append("empty_result")
        if provider in {"error", "tool_limit"}:
            score -= 0.5
            reasons.append(provider)
        if "LLM provider is not configured" in result:
            score -= 0.8
            reasons.append("provider_unconfigured")
        if len(result) > max(1200, len(task) * 20):
            score -= 0.05
            reasons.append("overlong")
        if re.search(r"(?i)I cannot|I can't", result) and "cannot" not in task.lower():
            score -= 0.05
            reasons.append("possible_refusal")

        trace = trace or {}
        if trace.get("errors"):
            score -= min(0.15, 0.03 * len(trace["errors"]))
            reasons.append("runtime_error_signal")
        if trace.get("verification", {}).get("passed") is False:
            score -= 0.2
            reasons.append("verification_failed")
        if any(item.get("status") == "error" for item in trace.get("tool_calls", [])):
            score -= 0.15
            reasons.append("tool_error")
        if trace.get("status") == "success" and trace.get("verification", {}).get("passed") is True:
            reasons.append("verified_success")

        score = max(0.0, min(1.0, score))
        evaluation = EvaluationResult(score, score >= 0.6, tuple(dict.fromkeys(reasons)))

        record = {
            "timestamp": time.time(),
            "task": redact_sensitive(task),
            "provider": provider,
            "score": evaluation.score,
            "passed": evaluation.passed,
            "reasons": evaluation.reasons,
        }
        if trace:
            record["trace_id"] = trace.get("trace_id")
            record["session_id"] = trace.get("session_id")
            record["intent"] = trace.get("intent")
            record["agent"] = trace.get("actual_agent") or trace.get("planned_agent")
            record["status"] = trace.get("status")
            record["elapsed_ms"] = trace.get("elapsed_ms")
            record["verification"] = redact_sensitive(trace.get("verification", {}))
            record["tool_count"] = len(trace.get("tool_calls", []))

        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        return evaluation

    def recent(self, limit: int = 20) -> list[dict]:
        if limit <= 0 or not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict] = []
        for line in lines[-limit:]:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records
