from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from typing import Any


INTEL_GPU_TOP = shutil.which("intel_gpu_top")


class GPUSampler:
    """Background GPU telemetry sampler with cached latest state."""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._started = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._started:
            return

        self._started = True
        self._thread = threading.Thread(
            target=self._run,
            name="jenefar-gpu-sampler",
            daemon=True,
        )
        self._thread.start()

    def get(self) -> dict[str, Any] | None:
        self.start()

        # Give the sampler a short window to obtain its first real
        # hardware reading so the initial dashboard payload does not
        # incorrectly report "GPU unavailable".
        deadline = time.monotonic() + min(self.interval, 0.75)

        while time.monotonic() < deadline:
            with self._lock:
                if self._latest is not None:
                    return dict(self._latest)
            time.sleep(0.02)

        with self._lock:
            if self._latest is None:
                return None
            return dict(self._latest)

    def _run(self) -> None:
        while True:
            try:
                sample = self._sample()
                if sample is not None:
                    with self._lock:
                        self._latest = sample
            except Exception:
                pass

            time.sleep(self.interval)

    def _sample(self) -> dict[str, Any] | None:
        nvidia = self._nvidia()
        if nvidia is not None:
            return nvidia

        return self._intel()

    @staticmethod
    def _nvidia() -> dict[str, Any] | None:
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
                    "name": str(name),
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

    @staticmethod
    def _intel() -> dict[str, Any] | None:
        if not INTEL_GPU_TOP:
            return None

        try:
            completed = subprocess.run(
                [
                    INTEL_GPU_TOP,
                    "-J",
                    "-s",
                    "500",
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


GPU_SAMPLER = GPUSampler()
