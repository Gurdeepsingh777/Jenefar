from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
)
_MAX_STRING_LENGTH = 4000


def redact_sensitive(value: Any) -> Any:
    """Recursively redact common credentials and bound diagnostic payloads."""
    if isinstance(value, str):
        result = value
        result = _SENSITIVE_PATTERNS[0].sub("Bearer [REDACTED]", result)
        result = _SENSITIVE_PATTERNS[1].sub(lambda match: f"{match.group(1)}=[REDACTED]", result)
        for pattern in _SENSITIVE_PATTERNS[2:]:
            result = pattern.sub("[REDACTED_CREDENTIAL]", result)
        if len(result) > _MAX_STRING_LENGTH:
            result = result[:_MAX_STRING_LENGTH] + "…[TRUNCATED]"
        return result
    if isinstance(value, dict):
        return {str(key): redact_sensitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, set):
        return sorted(redact_sensitive(item) for item in value)
    return value


@dataclass
class ExecutionTrace:
    """Structured, append-only trace for one Jenefar task execution."""

    trace_id: str = field(default_factory=lambda: uuid4().hex)
    session_id: str = ""
    task: str = ""
    source: str = "user"
    event_id: int | None = None
    intent: str = ""
    planned_agent: str = ""
    actual_agent: str = ""
    planner_confidence: float = 0.0
    provider: str = ""
    model_role: str = ""
    connectivity: str = "unknown"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"
    verification: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def elapsed_ms(self) -> float | None:
        if self.finished_at is None:
            return None
        return max(0.0, (self.finished_at - self.started_at) * 1000.0)

    def finish(self, *, status: str, provider: str = "", verification: dict[str, Any] | None = None) -> None:
        self.finished_at = time.time()
        self.status = status
        if provider:
            self.provider = provider
        if verification is not None:
            self.verification = dict(verification)

    def add_tool_call(self, *, name: str, status: str, approval_required: bool = False, result: Any = None) -> None:
        item: dict[str, Any] = {
            "name": name,
            "status": status,
            "approval_required": bool(approval_required),
            "timestamp": time.time(),
        }
        if result is not None:
            item["result"] = result
        self.tool_calls.append(item)

    def add_error(self, error: str) -> None:
        if error:
            self.errors.append(str(error))

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["elapsed_ms"] = self.elapsed_ms()
        return value


class TraceStore:
    """Small JSONL store for runtime traces; safe for append-only local diagnostics."""

    def __init__(self, path: str | Path = "data/execution_traces.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, trace: ExecutionTrace) -> None:
        payload = redact_sensitive(trace.as_dict())
        payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0 or not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def summary(self, limit: int = 200) -> dict[str, Any]:
        records = self.recent(limit)
        total = len(records)
        passed = sum(1 for item in records if item.get("status") == "success")
        failures = sum(1 for item in records if item.get("status") in {"error", "failed"})
        approval = sum(1 for item in records if any(bool(tool.get("approval_required")) for tool in item.get("tool_calls", [])))
        durations = [float(item["elapsed_ms"]) for item in records if item.get("elapsed_ms") is not None]
        ordered = sorted(durations)
        def percentile(percent: float) -> float:
            if not ordered:
                return 0.0
            index = min(len(ordered) - 1, int(round((percent / 100) * (len(ordered) - 1))))
            return ordered[index]
        try:
            slow_threshold = max(0.0, float(os.getenv("JENEFAR_SLOW_TRACE_MS", "10000")))
        except ValueError:
            slow_threshold = 10000.0
        statuses: dict[str, int] = {}
        for item in records:
            state = str(item.get("status") or "unknown")
            statuses[state] = statuses.get(state, 0) + 1
        return {
            "traces": total,
            "success_rate": (passed / total) if total else 0.0,
            "failure_rate": (failures / total) if total else 0.0,
            "approval_traces": approval,
            "average_elapsed_ms": (sum(durations) / len(durations)) if durations else 0.0,
            "p50_elapsed_ms": percentile(50),
            "p95_elapsed_ms": percentile(95),
            "max_elapsed_ms": max(durations) if durations else 0.0,
            "slow_trace_count": sum(1 for item in records if float(item.get("elapsed_ms") or 0) >= slow_threshold),
            "slow_trace_threshold_ms": slow_threshold,
            "providers": sorted({str(item.get("provider", "")) for item in records if item.get("provider")}),
            "agents": sorted({str(item.get("actual_agent", "")) for item in records if item.get("actual_agent")}),
            "statuses": dict(sorted(statuses.items())),
            "last_status": str(records[-1].get("status")) if records else "",
        }


__all__ = ["ExecutionTrace", "TraceStore", "redact_sensitive"]
