"""Small, optional health-check boundary for a local Free Claude Code gateway."""

from __future__ import annotations

import os
from urllib.error import URLError
from urllib.request import urlopen


def fcc_base_url() -> str:
    """Return the FCC OpenAI-compatible API base URL."""
    return os.getenv("FCC_BASE_URL", "http://127.0.0.1:8082/v1").strip().rstrip("/")


def fcc_api_key() -> str:
    """Return the optional FCC proxy token or a non-secret local placeholder."""
    return os.getenv("FCC_API_KEY", "").strip() or "fcc-local"


def fcc_model() -> str:
    """Return the model identifier configured in FCC's model settings."""
    return os.getenv(
        "FCC_MODEL",
        "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b",
    ).strip()


def fcc_health_url() -> str:
    """FCC exposes an unauthenticated /health endpoint beside its /v1 API."""
    base = fcc_base_url()
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/health"


def fcc_is_healthy(timeout: float | None = None) -> bool:
    """Return False on connection errors, non-200 responses, or malformed health."""
    if timeout is None:
        try:
            timeout = max(0.2, float(os.getenv("FCC_HEALTH_TIMEOUT_SECONDS", "1.5")))
        except ValueError:
            timeout = 1.5
    try:
        with urlopen(fcc_health_url(), timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = response.read(4096).decode("utf-8", errors="replace")
        return '"healthy"' in payload or '"status": "healthy"' in payload.replace("\\n", " ")
    except (OSError, URLError, TimeoutError, ValueError):
        return False


__all__ = ["fcc_api_key", "fcc_base_url", "fcc_health_url", "fcc_is_healthy", "fcc_model"]
