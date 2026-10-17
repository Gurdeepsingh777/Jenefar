from __future__ import annotations

from jenefar.avatar.system_metrics import read_system_metrics


def test_system_metrics_are_measured_and_have_a_real_timestamp():
    metrics = read_system_metrics()

    assert metrics["available"] is True
    assert metrics["sampled_at"].endswith("+00:00")
    assert 0 <= metrics["cpu"]["usage_percent"] <= 100
    assert metrics["cpu"]["logical_cores"] >= 1
    assert 0 <= metrics["ram"]["usage_percent"] <= 100
    assert metrics["ram"]["total_bytes"] > 0
    assert 0 <= metrics["ram"]["used_bytes"] <= metrics["ram"]["total_bytes"]
    assert metrics["process"]["memory_bytes"] > 0
    assert isinstance(metrics["gpu"]["available"], bool)


def test_gpu_unavailable_is_reported_without_a_fake_percentage(monkeypatch):
    from jenefar.avatar import system_metrics

    monkeypatch.setattr(system_metrics.shutil, "which", lambda _name: None)
    gpu = system_metrics._gpu_metrics()

    assert gpu["available"] is False
    assert gpu["usage_percent"] is None
    assert gpu["memory_used_mb"] is None
