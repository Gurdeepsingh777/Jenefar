from __future__ import annotations

import json
import shutil
import subprocess
import time

import psutil


INTEL_GPU_TOP = shutil.which("intel_gpu_top")


def get_cpu() -> float:
    return round(psutil.cpu_percent(interval=0.2), 1)


def get_ram() -> dict:
    memory = psutil.virtual_memory()

    return {
        "percent": round(memory.percent, 1),
        "used_gb": round(memory.used / 1024**3, 2),
        "total_gb": round(memory.total / 1024**3, 2),
    }


def _get_nvidia_gpu() -> dict | None:
    """Return NVIDIA GPU telemetry when NVML is available."""
    try:
        import pynvml

        pynvml.nvmlInit()

        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            name = pynvml.nvmlDeviceGetName(handle)

            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")

            return {
                "available": True,
                "vendor": "NVIDIA",
                "name": name,
                "usage": round(float(util.gpu), 1),
                "power_w": None,
                "memory_used_gb": round(mem.used / 1024**3, 2),
                "memory_total_gb": round(mem.total / 1024**3, 2),
            }
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

    except Exception:
        return None


def _get_intel_gpu() -> dict | None:
    """Read Intel GPU utilization through intel_gpu_top JSON output."""
    if not INTEL_GPU_TOP:
        return None

    try:
        completed = subprocess.run(
            [
                INTEL_GPU_TOP,
                "-J",
                "-s",
                "250",
                "-o",
                "-",
                "-n",
                "2",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )

        if completed.returncode != 0 or not completed.stdout.strip():
            return None

        samples = json.loads(completed.stdout)

        if not isinstance(samples, list) or not samples:
            return None

        sample = samples[-1]

        engines = sample.get("engines", {})

        render_usage = 0.0
        max_engine_usage = 0.0

        for engine_name, engine_data in engines.items():
            busy = float(engine_data.get("busy", 0.0))
            max_engine_usage = max(max_engine_usage, busy)

            if engine_name == "Render/3D":
                render_usage = busy

        power = sample.get("power", {})
        gpu_power = power.get("GPU")

        return {
            "available": True,
            "vendor": "Intel",
            "name": "Intel GPU",
            "usage": round(max_engine_usage, 1),
            "render_3d_usage": round(render_usage, 1),
            "power_w": (
                round(float(gpu_power), 3)
                if gpu_power is not None
                else None
            ),
            "memory_used_gb": None,
            "memory_total_gb": None,
        }

    except (
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ):
        return None


def get_gpu() -> dict:
    """Return the first available GPU telemetry backend."""
    nvidia = _get_nvidia_gpu()

    if nvidia is not None:
        return nvidia

    intel = _get_intel_gpu()

    if intel is not None:
        return intel

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
