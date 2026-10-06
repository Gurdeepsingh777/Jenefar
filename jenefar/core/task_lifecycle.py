from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"queued", "running", "waiting_approval", "cancelling"}


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
            "task": self.task,
            "agent": self.agent,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": elapsed_ms,
            "reason": self.reason,
            "provider": self.provider,
            "metadata": dict(self.metadata),
        }


class TaskLifecycle:
    """Thread-safe admission, state transitions, and bounded task history."""

    def __init__(self, max_history: int = 100):
        self._lock = threading.RLock()
        self._records: dict[str, TaskRecord] = {}
        self._history: deque[str] = deque(maxlen=max(1, int(max_history)))
        self._active_id: str | None = None

    def admit(self, task_id: str, task: str, *, agent: str = "") -> TaskRecord | None:
        with self._lock:
            if self._active_id is not None:
                active = self._records.get(self._active_id)
                if active is not None and active.state not in TERMINAL_STATES:
                    return None
                self._active_id = None
            record = TaskRecord(task_id=task_id, task=task, agent=agent)
            self._records[task_id] = record
            self._history.append(task_id)
            self._active_id = task_id
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
                record.reason = str(reason)
            if provider:
                record.provider = str(provider)
            if metadata:
                record.metadata.update(metadata)
            if state in TERMINAL_STATES:
                record.finished_at = time.time()
                if self._active_id == task_id:
                    self._active_id = None
            return record.as_dict()

    def active(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_id is None:
                return None
            record = self._records.get(self._active_id)
            return record.as_dict() if record is not None else None

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._history)[-max(1, int(limit)):]
            return [self._records[item].as_dict() for item in ids if item in self._records]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = self.active()
            return {
                "active": active,
                "history": self.history(20),
                "active_task_id": self._active_id or "",
                "active_count": 1 if active else 0,
            }


__all__ = ["ACTIVE_STATES", "TERMINAL_STATES", "TaskLifecycle", "TaskRecord"]
