"""Real host telemetry for the local Jenefar browser dashboard.

Values are sampled from the OS at request time. Unsupported sensors are reported
as unavailable instead of showing illustrative/demo numbers.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone


def _gpu_metrics() -> dict:
    """Return measured NVIDIA telemetry where nvidia-smi is available."""
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {
            "available": False,
            "usage_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "reason": "nvidia-smi unavailable",
        }

    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=1.5,
        )
        samples = []
        for line in result.stdout.splitlines():
            parts = [item.strip() for item in line.split(",")]
            if len(parts) != 3:
                continue
            samples.append(tuple(float(item) for item in parts))
        if not samples:
            raise ValueError("nvidia-smi returned no GPU samples")
        return {
            "available": True,
            "usage_percent": round(sum(item[0] for item in samples) / len(samples), 1),
            "memory_used_mb": round(sum(item[1] for item in samples)),
            "memory_total_mb": round(sum(item[2] for item in samples)),
            "reason": None,
        }
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {
            "available": False,
            "usage_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "reason": f"GPU telemetry unavailable: {type(exc).__name__}",
        }


def read_system_metrics() -> dict:
    """Sample system CPU/RAM and Jenefar process memory using psutil."""
    try:
        import psutil
    except ImportError as exc:  # pragma: no cover - covered by runtime packaging
        raise RuntimeError("System telemetry requires the 'psutil' package.") from exc

    memory = psutil.virtual_memory()
    process = psutil.Process(os.getpid())
    process_memory = process.memory_info()

    return {
        "available": True,
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "cpu": {
            "usage_percent": round(float(psutil.cpu_percent(interval=0.12)), 1),
            "logical_cores": psutil.cpu_count(logical=True),
        },
        "ram": {
            "usage_percent": round(float(memory.percent), 1),
            "used_bytes": int(memory.used),
            "total_bytes": int(memory.total),
            "available_bytes": int(memory.available),
        },
        "process": {
            "memory_bytes": int(process_memory.rss),
            "memory_percent": round(float(process.memory_percent()), 2),
        },
        "gpu": _gpu_metrics(),
    }


__all__ = ["read_system_metrics"]
