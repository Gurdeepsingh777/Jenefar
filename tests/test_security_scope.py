from __future__ import annotations

from types import SimpleNamespace

import pytest

from jenefar.execution.scope import ScopePolicy
from jenefar.tools.security import ScopedSecurityToolExecutor


def test_nmap_preserves_the_full_authorized_cidr(monkeypatch):
    captured = {}

    monkeypatch.setattr("jenefar.tools.security.shutil.which", lambda tool: "/usr/bin/nmap")

    def fake_run(command, *, shell, capture_output, text, timeout):
        captured["command"] = command
        captured["shell"] = shell
        captured["timeout"] = timeout
        return SimpleNamespace(returncode=0, stdout="Nmap done", stderr="")

    monkeypatch.setattr("jenefar.tools.security.subprocess.run", fake_run)
    executor = ScopedSecurityToolExecutor(ScopePolicy(["192.168.29.0/24"]))

    result = executor.run(tool="nmap", target="192.168.29.0/24", timeout=60)

    assert result["returncode"] == 0
    assert captured["shell"] is False
    assert captured["command"][-1] == "192.168.29.0/24"
    assert "192.168.29.0/24" in result["command"]


def test_nmap_rejects_cidr_not_fully_inside_authorized_scope(monkeypatch):
    executor = ScopedSecurityToolExecutor(ScopePolicy(["192.168.29.0/24"]))
    with pytest.raises(PermissionError):
        executor.run(tool="nmap", target="192.168.0.0/16", timeout=60)


def test_web_profiles_reject_cidr_ranges(monkeypatch):
    executor = ScopedSecurityToolExecutor(ScopePolicy(["192.168.29.0/24"]))
    with pytest.raises(ValueError, match="Nmap profile only"):
        executor.run(tool="whatweb", target="192.168.29.0/24", timeout=30)
