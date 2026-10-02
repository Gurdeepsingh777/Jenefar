from __future__ import annotations

import socket

from jenefar.monitoring.server import (
    MonitoringServer,
    monitoring_endpoint_healthy,
    monitoring_port_available,
)


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_monitoring_server_starts_and_stops():
    port = free_local_port()

    server = MonitoringServer(port=port)

    assert not server.running
    assert monitoring_port_available("127.0.0.1", port)

    server.start()

    try:
        assert server.running
        assert server.url == f"ws://127.0.0.1:{port}"
        assert monitoring_endpoint_healthy("127.0.0.1", port)
    finally:
        server.stop()

    assert not server.running
    assert monitoring_port_available("127.0.0.1", port)


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
    assert "monitoring_server_owned" in source


def test_existing_monitor_is_not_reported_as_owned():
    port = free_local_port()
    owner = MonitoringServer(port=port)
    owner.start()

    try:
        assert monitoring_endpoint_healthy("127.0.0.1", port)
    finally:
        owner.stop()


def test_start_helper_reuses_existing_endpoint():
    port = free_local_port()
    owner = MonitoringServer(port=port)
    owner.start()

    try:
        from jenefar.monitoring.server import start_monitoring_server

        reused = start_monitoring_server(
            host="127.0.0.1",
            port=port,
        )

        assert reused.host == "127.0.0.1"
        assert reused.port == port
        assert not reused.running
    finally:
        owner.stop()
