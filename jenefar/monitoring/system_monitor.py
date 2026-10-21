from __future__ import annotations

import time

import psutil

from .gpu_sampler import GPU_SAMPLER


def get_cpu() -> float:
    """Return system-wide CPU utilisation as a percentage."""
    return round(psutil.cpu_percent(interval=0.08), 1)


def get_ram() -> dict:
    """Return current RAM usage and capacity in GiB."""
    memory = psutil.virtual_memory()
    return {
        "percent": round(memory.percent, 1),
        "used_gb": round(memory.used / 1024**3, 2),
        "total_gb": round(memory.total / 1024**3, 2),
    }


def get_gpu() -> dict:
    """Return cached NVIDIA/Intel telemetry, or a stable unavailable shape."""
    gpu = GPU_SAMPLER.get()
    if gpu is not None:
        return gpu
    return {
        "available": False,
        "vendor": None,
        "name": None,
        "usage": 0.0,
        "power_w": None,
        "memory_used_gb": None,
        "memory_total_gb": None,
    }


def get_process_memory() -> dict:
    """Return Jenefar's own resident memory separately from host-wide RAM."""
    import os

    try:
        process = psutil.Process(os.getpid())
        rss = int(process.memory_info().rss)
        return {
            "memory_bytes": rss,
            "memory_mb": round(rss / 1024**2, 1),
            "memory_percent": round(float(process.memory_percent()), 2),
        }
    except (OSError, psutil.Error):
        return {"memory_bytes": None, "memory_mb": None, "memory_percent": None}


def get_system_stats() -> dict:
    """Build the JSON-safe payload broadcast to local dashboard clients."""
    return {
        "timestamp": time.time(),
        "cpu": get_cpu(),
        "ram": get_ram(),
        "process": get_process_memory(),
        "gpu": get_gpu(),
    }


__all__ = ["get_cpu", "get_ram", "get_gpu", "get_system_stats"]
