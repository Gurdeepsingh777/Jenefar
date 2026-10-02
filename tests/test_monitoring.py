from __future__ import annotations

import json
import subprocess

from jenefar.monitoring import system_monitor


def test_get_ram_returns_real_memory_shape():
    result = system_monitor.get_ram()

    assert set(result) == {"percent", "used_gb", "total_gb"}
    assert 0 <= result["percent"] <= 100
    assert result["used_gb"] >= 0
    assert result["total_gb"] > 0


def test_get_system_stats_contains_real_telemetry_shape():
    result = system_monitor.get_system_stats()

    assert isinstance(result["timestamp"], float)
    assert isinstance(result["cpu"], float)

    assert "percent" in result["ram"]
    assert "used_gb" in result["ram"]
    assert "total_gb" in result["ram"]

    assert "available" in result["gpu"]
    assert "vendor" in result["gpu"]
    assert "usage" in result["gpu"]


def test_intel_gpu_json_parser_reads_render_usage(monkeypatch):
    sample = [
        {
            "period": {"duration": 250.0, "unit": "ms"},
            "power": {"GPU": 0.42, "Package": 6.2, "unit": "W"},
            "engines": {
                "Render/3D": {
                    "busy": 17.354828,
                    "sema": 0.0,
                    "wait": 0.0,
                    "unit": "%",
                },
                "Blitter": {
                    "busy": 2.0,
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

    from jenefar.monitoring import gpu_sampler

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
    assert result["usage"] == 17.4
    assert result["render_3d_usage"] == 17.4
    assert result["power_w"] == 0.42


def test_monitoring_server_uses_modern_websocket_api():
    from pathlib import Path

    source = Path("jenefar/monitoring/server.py").read_text(encoding="utf-8")

    assert "from websockets.asyncio.server import serve" in source
    assert "await websocket.wait_closed()" in source
    assert "HOST = \"127.0.0.1\"" in source
    assert "PORT = 8765" in source


def test_browser_uses_live_system_telemetry():
    from pathlib import Path

    html = Path("jenefar/avatar/web/index.html").read_text(encoding="utf-8")
    app = Path("jenefar/avatar/web/app.js").read_text(encoding="utf-8")

    assert 'id="cpu-value"' in html
    assert 'id="ram-value"' in html
    assert 'id="gpu-value"' in html
    assert "new WebSocket" in app
    assert "get_system_stats" not in app
    assert "updateSystemTelemetry" in app
