from __future__ import annotations

import threading
import time


class CancellationToken:
    """Thread-safe cooperative cancellation token for a live Jenefar task."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.created_at = time.time()
        self.cancelled_at: float | None = None
        self.reason = ""

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self, reason: str = "cancelled by user") -> bool:
        if self._event.is_set():
            return False
        self.reason = str(reason or "cancelled")
        self.cancelled_at = time.time()
        self._event.set()
        return True

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TimeoutError(f"Jenefar execution cancelled: {self.reason}")

    def as_dict(self) -> dict[str, object]:
        return {
            "cancelled": self.cancelled,
            "reason": self.reason,
            "created_at": self.created_at,
            "cancelled_at": self.cancelled_at,
        }


__all__ = ["CancellationToken"]