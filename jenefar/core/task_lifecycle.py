from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jenefar.evaluation.trace import redact_sensitive


TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"queued", "running", "waiting_approval", "cancelling"}


def _history_limit(value: int | str | None) -> int:
    if value is None:
        value = os.getenv("JENEFAR_TASK_HISTORY_LIMIT", "100")
    try:
        return max(1, min(int(value), 1000))
    except (TypeError, ValueError):
        return 100


@dataclass
class TaskRecord:
    task_id: str
    task: str
    agent: str = ""
    state: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    reason: str = ""
    provider: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        now = self.finished_at or time.time()
        elapsed_ms = max(0.0, (now - self.started_at) * 1000.0) if self.started_at else None
        return {
            "task_id": self.task_id,
            "task": redact_sensitive(self.task),
            "agent": redact_sensitive(self.agent),
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": elapsed_ms,
            "reason": redact_sensitive(self.reason),
            "provider": redact_sensitive(self.provider),
            "metadata": redact_sensitive(dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TaskRecord":
        return cls(
            task_id=str(value.get("task_id") or ""),
            task=str(value.get("task") or ""),
            agent=str(value.get("agent") or ""),
            state=str(value.get("state") or "completed"),
            created_at=float(value.get("created_at") or time.time()),
            started_at=float(value["started_at"]) if value.get("started_at") is not None else None,
            finished_at=float(value["finished_at"]) if value.get("finished_at") is not None else None,
            reason=str(value.get("reason") or ""),
            provider=str(value.get("provider") or ""),
            metadata={},
        )


class TaskLifecycle:
    """Thread-safe task admission plus bounded, privacy-safe persistent history."""

    def __init__(
        self,
        max_history: int | None = None,
        history_path: str | Path | None = None,
    ):
        self._lock = threading.RLock()
        self._records: dict[str, TaskRecord] = {}
        self._history: deque[str] = deque(maxlen=_history_limit(max_history))
        self._history_path = Path(
            history_path
            or os.getenv("JENEFAR_TASK_HISTORY_PATH", "data/task_history.jsonl")
        )
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._active_id: str | None = None
        self._load_persisted_history()

    @property
    def history_path(self) -> Path:
        return self._history_path

    @property
    def max_history(self) -> int:
        return self._history.maxlen or 100

    def _load_persisted_history(self) -> None:
        if not self._history_path.exists():
            return
        try:
            lines = self._history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        with self._lock:
            for line in lines[-self.max_history:]:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(value, dict) or value.get("state") not in TERMINAL_STATES:
                    continue
                try:
                    record = TaskRecord.from_dict(value)
                except (TypeError, ValueError):
                    continue
                if not record.task_id:
                    continue
                self._records[record.task_id] = record
                self._history.append(record.task_id)

    def _persistent_record(self, record: TaskRecord) -> dict[str, Any]:
        value = record.as_dict()
        # Do not persist arbitrary runtime metadata; task text/reason/provider/agent
        # are redacted and bounded by redact_sensitive().
        value["metadata"] = {}
        return value

    def _persist_locked(self) -> None:
        records = [
            self._persistent_record(self._records[item])
            for item in self._history
            if item in self._records and self._records[item].state in TERMINAL_STATES
        ]
        tmp = self._history_path.with_suffix(self._history_path.suffix + ".tmp")
        try:
            tmp.write_text(
                "".join(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
                    for item in records[-self.max_history:]
                ),
                encoding="utf-8",
            )
            os.replace(tmp, self._history_path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def admit(self, task_id: str, task: str, *, agent: str = "") -> TaskRecord | None:
        with self._lock:
            if self._active_id is not None:
                active = self._records.get(self._active_id)
                if active is not None and active.state not in TERMINAL_STATES:
                    return None
                self._active_id = None
            record = TaskRecord(
                task_id=str(task_id),
                task=redact_sensitive(str(task)),
                agent=redact_sensitive(str(agent)),
            )
            self._records[record.task_id] = record
            if len(self._history) == self.max_history:
                oldest = self._history[0]
                self._records.pop(oldest, None)
            self._history.append(record.task_id)
            self._active_id = record.task_id
            return record

    def transition(
        self,
        task_id: str,
        state: str,
        *,
        reason: str = "",
        provider: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return None
            if state not in ACTIVE_STATES | TERMINAL_STATES:
                raise ValueError(f"invalid task lifecycle state: {state}")
            if record.finished_at is not None and state not in TERMINAL_STATES:
                return record.as_dict()
            if record.started_at is None and state in {"running", "waiting_approval", "cancelling"}:
                record.started_at = time.time()
            record.state = state
            if reason:
                record.reason = redact_sensitive(str(reason))
            if provider:
                record.provider = redact_sensitive(str(provider))
            if metadata:
                record.metadata.update(redact_sensitive(metadata))
            if state in TERMINAL_STATES:
                record.finished_at = time.time()
                if self._active_id == task_id:
                    self._active_id = None
                self._persist_locked()
            return record.as_dict()

    def active(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_id is None:
                return None
            record = self._records.get(self._active_id)
            return record.as_dict() if record is not None else None

    def history(
        self,
        limit: int = 20,
        *,
        search: str = "",
        state: str = "",
        agent: str = "",
        provider: str = "",
    ) -> list[dict[str, Any]]:
        with self._lock:
            wanted = max(1, min(int(limit), self.max_history))
            query = str(search or "").strip().lower()
            state_filter = str(state or "").strip().lower()
            agent_filter = str(agent or "").strip().lower()
            provider_filter = str(provider or "").strip().lower()
            records = []
            for item in reversed(self._history):
                record = self._records.get(item)
                if record is None:
                    continue
                value = record.as_dict()
                haystack = " ".join(
                    str(value.get(key) or "").lower()
                    for key in ("task_id", "task", "reason", "agent", "provider", "state")
                )
                if query and query not in haystack:
                    continue
                if state_filter and str(value["state"]).lower() != state_filter:
                    continue
                if agent_filter and str(value["agent"]).lower() != agent_filter:
                    continue
                if provider_filter and str(value["provider"]).lower() != provider_filter:
                    continue
                records.append(value)
                if len(records) >= wanted:
                    break
            return records

    def snapshot(self, limit: int = 20) -> dict[str, Any]:
        with self._lock:
            active = self.active()
            return {
                "active": active,
                "history": self.history(limit),
                "active_task_id": self._active_id or "",
                "active_count": 1 if active else 0,
                "history_persistent": True,
                "history_limit": self.max_history,
            }

    def query_history(
        self,
        *,
        search: str = "",
        state: str = "",
        agent: str = "",
        provider: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        records = self.history(
            limit,
            search=search,
            state=state,
            agent=agent,
            provider=provider,
        )
        return {
            "items": records,
            "count": len(records),
            "limit": max(1, min(int(limit), self.max_history)),
            "history_limit": self.max_history,
            "persistent": True,
        }


__all__ = ["ACTIVE_STATES", "TERMINAL_STATES", "TaskLifecycle", "TaskRecord"]
