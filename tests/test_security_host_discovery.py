from types import SimpleNamespace

import pytest

from jenefar.execution.scope import ScopePolicy
from jenefar.tools.security import ScopedSecurityToolExecutor


def test_live_host_scan_keeps_cidr_and_parses_hosts(monkeypatch):
    captured = {}
    xml = '''<nmaprun><host><status state="up"/><address addr="192.168.1.20" addrtype="ipv4"/><hostnames><hostname name="printer.local"/></hostnames></host><host><status state="down"/><address addr="192.168.1.21" addrtype="ipv4"/></host></nmaprun>'''
    monkeypatch.setattr("jenefar.tools.security.shutil.which", lambda _: "/usr/bin/nmap")

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout=xml, stderr="")

    monkeypatch.setattr("jenefar.tools.security.subprocess.run", fake_run)
    executor = ScopedSecurityToolExecutor(ScopePolicy(["192.168.1.0/24"]))

    result = executor.run(tool="nmap", target="192.168.1.0/24", mode="live_hosts")

    assert captured["command"][-1] == "192.168.1.0/24"
    assert "-sn" in captured["command"]
    assert "--unprivileged" in captured["command"]
    assert result["profile"] == "host_discovery"
    assert result["live_host_count"] == 1
    assert result["hosts"] == [
        {"addresses": ["192.168.1.20"], "hostnames": ["printer.local"]}
    ]


def test_live_host_scan_rejects_range_outside_authorized_scope(monkeypatch):
    monkeypatch.setattr("jenefar.tools.security.shutil.which", lambda _: "/usr/bin/nmap")
    executor = ScopedSecurityToolExecutor(ScopePolicy(["192.168.1.0/24"]))

    with pytest.raises(PermissionError):
        executor.run(tool="nmap", target="192.168.0.0/16", mode="live_hosts")
