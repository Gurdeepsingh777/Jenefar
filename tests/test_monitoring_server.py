from __future__ import annotations

import socket

from jenefar.monitoring.server import MonitoringServer


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_monitoring_server_starts_and_stops():
    port = free_local_port()

    server = MonitoringServer(port=port)

    assert not server.running

    server.start()

    try:
        assert server.running
        assert server.url == f"ws://127.0.0.1:{port}"
    finally:
        server.stop()

    assert not server.running


def test_monitoring_server_exposes_expected_configuration():
    server = MonitoringServer()

    assert server.host == "127.0.0.1"
    assert server.port == 8765
    assert server.url == "ws://127.0.0.1:8765"


def test_run_integrates_monitoring_runtime():
    from pathlib import Path

    source = Path("run.py").read_text(encoding="utf-8")

    assert "start_monitoring_server" in source
    assert "monitoring_server.stop()" in source
