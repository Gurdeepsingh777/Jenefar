from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from pathlib import Path


@dataclass(frozen=True)
class EvaluationResult:
    score: float
    passed: bool
    reasons: tuple[str, ...]


class EvaluationLoop:
    """Runtime quality evaluation and learning-signal collection."""

    def __init__(self, path: str | Path = "data/evaluations.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def evaluate(self, task: str, result: str, provider: str = "") -> EvaluationResult:
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

        score = max(0.0, min(1.0, score))
        evaluation = EvaluationResult(score, score >= 0.6, tuple(reasons))

        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "timestamp": time.time(),
                "task": task,
                "provider": provider,
                "score": evaluation.score,
                "passed": evaluation.passed,
                "reasons": evaluation.reasons,
            }, ensure_ascii=False) + "\n")

        return evaluation

    def recent(self, limit: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:] if line.strip()]
