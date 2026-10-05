from __future__ import annotations

import os
import time
from typing import Any

from jenefar.evaluation.trace import TraceStore


def build_runtime_snapshot(
    *,
    runtime_context: dict[str, Any] | None = None,
    self_healing: Any = None,
    trace_store: TraceStore | None = None,
    provider_pool: Any = None,
) -> dict[str, Any]:
    """Build a credential-safe snapshot for the live runtime dashboard."""
    context = dict(runtime_context or {})
    traces = (trace_store or TraceStore()).summary(200)
    healing = self_healing.health_snapshot() if self_healing is not None else {}
    providers = provider_pool.latency_status() if provider_pool is not None else {}
    deadline = context.get("deadline_monotonic")
    remaining = None
    if deadline is not None:
        try:
            remaining = max(0.0, float(deadline) - time.monotonic())
        except (TypeError, ValueError):
            remaining = None
    return {
        "schema_version": 1,
        "timestamp": time.time(),
        "current": {
            "state": str(context.get("state") or "idle"),
            "task_id": str(context.get("task_id") or ""),
            "task": str(context.get("task") or ""),
            "agent": str(context.get("agent") or ""),
            "provider": str(context.get("provider") or ""),
            "model_role": str(context.get("model_role") or ""),
            "started_at": context.get("started_at"),
            "elapsed_ms": (
                max(0.0, (time.time() - float(context["started_at"])) * 1000.0)
                if context.get("started_at") is not None else None
            ),
            "budget_seconds": context.get("budget_seconds"),
            "remaining_seconds": remaining,
            "deadline_active": deadline is not None,
            "last_event": str(context.get("last_event") or ""),
        },
        "health": healing,
        "traces": traces,
        "providers": providers,
        "timeouts": {
            "provider_seconds": min(max(float(os.getenv("JENEFAR_PROVIDER_TIMEOUT_SECONDS", "45")), 5.0), 300.0),
            "local_llm_seconds": min(max(float(os.getenv("JENEFAR_LOCAL_LLM_TIMEOUT_SECONDS", "45")), 5.0), 300.0),
            "agent_seconds": min(max(float(os.getenv("JENEFAR_AGENT_TIMEOUT_SECONDS", "60")), 10.0), 300.0),
        },
    }


__all__ = ["build_runtime_snapshot"]
