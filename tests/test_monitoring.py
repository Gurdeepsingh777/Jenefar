from __future__ import annotations

import json
import subprocess

from jenefar.monitoring import system_monitor, gpu_sampler


def test_get_ram_returns_real_memory_shape():
    result = system_monitor.get_ram()
    assert set(result) == {"percent", "used_gb", "total_gb"}
    assert 0 <= result["percent"] <= 100
    assert result["used_gb"] >= 0
    assert result["total_gb"] > 0


def test_system_stats_has_stable_payload_shape(monkeypatch):
    monkeypatch.setattr(system_monitor, "get_cpu", lambda: 12.5)
    monkeypatch.setattr(system_monitor, "get_ram", lambda: {
        "percent": 40.0, "used_gb": 4.0, "total_gb": 10.0
    })
    monkeypatch.setattr(system_monitor, "get_gpu", lambda: {
        "available": False, "vendor": None, "name": None, "usage": 0.0,
        "power_w": None, "memory_used_gb": None, "memory_total_gb": None,
    })
    monkeypatch.setattr(system_monitor, "get_process_memory", lambda: {
        "memory_bytes": 1024 * 1024, "memory_mb": 1.0, "memory_percent": 0.01,
    })
    result = system_monitor.get_system_stats()
    assert isinstance(result["timestamp"], float)
    assert result["cpu"] == 12.5
    assert result["ram"]["percent"] == 40.0
    assert result["process"]["memory_mb"] == 1.0
    assert result["gpu"]["available"] is False


def test_intel_gpu_json_parser_reads_engine_load(monkeypatch):
    sample = [{
        "power": {"GPU": 0.42, "Package": 6.2, "unit": "W"},
        "engines": {
            "Render/3D": {"busy": 17.354828, "unit": "%"},
            "Blitter": {"busy": 2.0, "unit": "%"},
        },
    }]

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=json.dumps(sample), stderr=""
        )

    monkeypatch.setattr(gpu_sampler, "INTEL_GPU_TOP", "/usr/bin/intel_gpu_top")
    monkeypatch.setattr(gpu_sampler.subprocess, "run", fake_run)
    result = gpu_sampler.GPUSampler._intel()
    assert result is not None
    assert result["available"] is True
    assert result["vendor"] == "Intel"
    assert result["usage"] == 17.4
    assert result["render_3d_usage"] == 17.4
    assert result["power_w"] == 0.42


def test_intel_sampler_handles_missing_or_invalid_probe(monkeypatch):
    monkeypatch.setattr(gpu_sampler, "INTEL_GPU_TOP", None)
    assert gpu_sampler.GPUSampler._intel() is None
    monkeypatch.setattr(gpu_sampler, "INTEL_GPU_TOP", "/usr/bin/intel_gpu_top")

    def broken_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 2)

    monkeypatch.setattr(gpu_sampler.subprocess, "run", broken_run)
    assert gpu_sampler.GPUSampler._intel() is None


def test_gpu_cache_returns_a_copy():
    sampler = gpu_sampler.GPUSampler()
    sampler._latest = {"available": True, "vendor": "Intel", "usage": 5.0}
    result = sampler.get()
    assert result == sampler._latest
    assert result is not sampler._latest



def test_current_hud_is_wired_to_live_telemetry():
    from pathlib import Path

    html = Path("jenefar/avatar/web/index.html").read_text(encoding="utf-8")
    app = Path("jenefar/avatar/web/app.js").read_text(encoding="utf-8")

    for element_id in (
        "metric-cpu", "metric-cpu-value", "metric-cpu-detail",
        "metric-ram", "metric-ram-value", "metric-ram-detail",
        "metric-gpu", "metric-gpu-value", "metric-gpu-detail",
        "metrics-updated",
    ):
        assert f'id="{element_id}"' in html, f"HUD is missing {element_id}"

    assert "new WebSocket(socketUrl())" in app
    assert '":8765"' in app
    assert "function updateTelemetry(data)" in app
    assert "setupLiveSystemTelemetry" in app

def test_process_memory_is_reported_separately_from_system_ram():
    result = system_monitor.get_process_memory()
    assert set(result) == {"memory_bytes", "memory_mb", "memory_percent"}
    assert result["memory_bytes"] is None or result["memory_bytes"] > 0
    assert result["memory_mb"] is None or result["memory_mb"] > 0
