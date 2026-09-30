from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


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
        payload = trace.as_dict()
        payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\\n")

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
        approval = sum(
            1
            for item in records
            if any(bool(tool.get("approval_required")) for tool in item.get("tool_calls", []))
        )
        durations = [float(item["elapsed_ms"]) for item in records if item.get("elapsed_ms") is not None]
        return {
            "traces": total,
            "success_rate": (passed / total) if total else 0.0,
            "approval_traces": approval,
            "average_elapsed_ms": (sum(durations) / len(durations)) if durations else 0.0,
            "providers": sorted({str(item.get("provider", "")) for item in records if item.get("provider")}),
            "agents": sorted({str(item.get("actual_agent", "")) for item in records if item.get("actual_agent")}),
        }


__all__ = ["ExecutionTrace", "TraceStore"]
