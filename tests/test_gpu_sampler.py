from __future__ import annotations

import json
import subprocess

from jenefar.monitoring import gpu_sampler


def test_intel_sampler_parses_realistic_json(monkeypatch):
    sample = [
        {
            "period": {"duration": 500.0, "unit": "ms"},
            "power": {"GPU": 0.53, "Package": 7.1, "unit": "W"},
            "engines": {
                "Render/3D": {
                    "busy": 21.456,
                    "sema": 0.0,
                    "wait": 0.0,
                    "unit": "%",
                },
                "Blitter": {
                    "busy": 4.25,
                    "sema": 0.0,
                    "wait": 0.0,
                    "unit": "%",
                },
            },
        }
    ]

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(sample),
            stderr="",
        )

    monkeypatch.setattr(
        gpu_sampler,
        "INTEL_GPU_TOP",
        "/usr/bin/intel_gpu_top",
    )
    monkeypatch.setattr(
        gpu_sampler.subprocess,
        "run",
        fake_run,
    )

    result = gpu_sampler.GPUSampler._intel()

    assert result is not None
    assert result["available"] is True
    assert result["vendor"] == "Intel"
    assert result["usage"] == 21.5
    assert result["render_3d_usage"] == 21.5
    assert result["power_w"] == 0.53


def test_gpu_sampler_get_returns_copy():
    sampler = gpu_sampler.GPUSampler()

    sampler._latest = {
        "available": True,
        "vendor": "Intel",
        "usage": 5.0,
    }

    result = sampler.get()

    assert result == sampler._latest
    assert result is not sampler._latest


def test_system_monitor_uses_gpu_sampler(monkeypatch):
    from jenefar.monitoring import system_monitor

    expected = {
        "available": True,
        "vendor": "Intel",
        "name": "Intel GPU",
        "usage": 12.5,
        "power_w": 0.4,
        "memory_used_gb": None,
        "memory_total_gb": None,
    }

    monkeypatch.setattr(
        system_monitor.GPU_SAMPLER,
        "get",
        lambda: expected.copy(),
    )

    result = system_monitor.get_gpu()

    assert result["available"] is True
    assert result["vendor"] == "Intel"
    assert result["usage"] == 12.5
