from __future__ import annotations

import time

import psutil

from .gpu_sampler import GPU_SAMPLER


def get_cpu() -> float:
    return round(psutil.cpu_percent(interval=0.2), 1)


def get_ram() -> dict:
    memory = psutil.virtual_memory()

    return {
        "percent": round(memory.percent, 1),
        "used_gb": round(memory.used / 1024**3, 2),
        "total_gb": round(memory.total / 1024**3, 2),
    }


def get_gpu() -> dict:
    """Return the latest cached GPU telemetry."""
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


def get_system_stats() -> dict:
    return {
        "timestamp": time.time(),
        "cpu": get_cpu(),
        "ram": get_ram(),
        "gpu": get_gpu(),
    }
