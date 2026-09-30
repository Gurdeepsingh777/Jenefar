from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable, TypeVar


T = TypeVar("T")


TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "connection aborted",
    "temporarily unavailable",
    "service unavailable",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not 1 <= int(self.max_attempts) <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("invalid retry delay bounds")


@dataclass
class FailureState:
    failures: int = 0
    last_error: str = ""
    last_failure_at: float | None = None
    cooldown_until: float = 0.0


@dataclass
class RuntimeHealth:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    transient_failures: int = 0
    non_retryable_failures: int = 0
    consecutive_failures: int = 0
    last_error: str = ""
    last_failure_at: float | None = None
    last_success_at: float | None = None
    circuit_open_until: float = 0.0
    failure_state: dict[str, FailureState] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successes / self.calls if self.calls else 0.0

    @property
    def circuit_open(self) -> bool:
        return time.time() < self.circuit_open_until


class SelfHealingRuntime:
    """Bounded recovery for transient failures; never retries privileged actions."""

    def __init__(
        self,
        *,
        policy: RetryPolicy | None = None,
        circuit_threshold: int = 3,
        circuit_cooldown_seconds: float = 15.0,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self.circuit_threshold = max(1, int(circuit_threshold))
        self.circuit_cooldown_seconds = max(1.0, float(circuit_cooldown_seconds))
        self.health = RuntimeHealth()

    @staticmethod
    def is_transient_error(exc: BaseException) -> bool:
        message = f"{type(exc).__name__}: {exc}".lower()
        return any(marker in message for marker in TRANSIENT_MARKERS)

    @staticmethod
    def is_retry_safe(operation_name: str, metadata: dict | None = None) -> bool:
        meta = metadata or {}
        if meta.get("approval_required") or meta.get("security_action"):
            return False
        name = str(operation_name).lower()
        unsafe_markers = (
            "terminal", "edit", "write", "delete", "move", "rename",
            "kali_tool_execute", "connector_execute", "robot", "mqtt",
            "ros2", "desktop_click", "desktop_type", "schedule_create",
        )
        return not any(marker in name for marker in unsafe_markers)

    def _record_failure(self, operation_name: str, exc: BaseException) -> None:
        message = f"{type(exc).__name__}: {exc}"
        self.health.failures += 1
        self.health.consecutive_failures += 1
        self.health.last_error = message
        self.health.last_failure_at = time.time()
        state = self.health.failure_state.setdefault(operation_name, FailureState())
        state.failures += 1
        state.last_error = message
        state.last_failure_at = self.health.last_failure_at
        if self.health.consecutive_failures >= self.circuit_threshold:
            self.health.circuit_open_until = time.time() + self.circuit_cooldown_seconds
            state.cooldown_until = self.health.circuit_open_until

    def _record_success(self) -> None:
        self.health.successes += 1
        self.health.consecutive_failures = 0
        self.health.last_success_at = time.time()

    def run(
        self,
        operation_name: str,
        operation: Callable[[], T],
        *,
        metadata: dict | None = None,
    ) -> T:
        self.health.calls += 1
        safe_retry = self.is_retry_safe(operation_name, metadata)
        attempts = self.policy.max_attempts if safe_retry else 1

        if safe_retry and self.health.circuit_open:
            raise RuntimeError(
                f"runtime circuit open for '{operation_name}' until "
                f"{self.health.circuit_open_until:.3f}"
            )

        for attempt in range(1, attempts + 1):
            try:
                result = operation()
                self._record_success()
                return result
            except Exception as exc:
                transient = self.is_transient_error(exc)
                if not transient or attempt >= attempts:
                    if not transient:
                        self.health.non_retryable_failures += 1
                    else:
                        self.health.transient_failures += 1
                    self._record_failure(operation_name, exc)
                    raise

                self.health.transient_failures += 1
                self.health.retries += 1
                delay = min(
                    self.policy.max_delay_seconds,
                    self.policy.base_delay_seconds * (2 ** (attempt - 1)),
                )
                if delay:
                    time.sleep(delay)

        raise RuntimeError("unreachable retry state")


__all__ = ["RetryPolicy", "RuntimeHealth", "SelfHealingRuntime"]
