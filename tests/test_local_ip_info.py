import json
from types import SimpleNamespace

from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.core.planner import Planner
from jenefar.tools import network_info


def test_check_my_ip_is_a_direct_ip_info_request_not_a_scan():
    assert JenefarOrchestrator._is_ip_info_query("check my ip")
    assert JenefarOrchestrator._is_ip_info_query("What's my public IP address?")
    assert JenefarOrchestrator._is_ip_info_query("mera ip batao")
    assert not JenefarOrchestrator._is_ip_info_query("scan my network with nmap")
    assert not JenefarOrchestrator._is_ip_info_query("run a port scan against my lab")


class _FakeSession:
    session_id = "test-session"

    def add(self, *_args, **_kwargs):
        pass


class _FakeMemory:
    def record_message(self, *_args, **_kwargs):
        pass


class _FakeGraph:
    def learn_text(self, *_args, **_kwargs):
        pass


class _FakeToolBroker:
    def __init__(self):
        self.calls = []

    def invoke(self, name, arguments):
        self.calls.append((name, arguments))
        return json.dumps({
            "status": "ok",
            "result": {
                "local_ipv4": [{"address": "192.168.1.20", "interface": "wlan0"}],
                "local_ipv6": [],
                "public_ipv4": "203.0.113.20",
                "public_ipv4_status": "available",
                "network_scan_performed": False,
            },
        })


def test_orchestrator_check_my_ip_uses_read_only_ip_tool_and_skips_llm():
    orchestrator = object.__new__(JenefarOrchestrator)
    orchestrator.pending_approval_workflows = {}
    orchestrator.session = _FakeSession()
    orchestrator.memory_engine = _FakeMemory()
    orchestrator.graph = _FakeGraph()
    orchestrator.state = None
    orchestrator.config = SimpleNamespace(single_turn_sleep=False)
    orchestrator.tool_broker = _FakeToolBroker()
    orchestrator._avatar_state = lambda *_args, **_kwargs: None

    reply = orchestrator.handle("check my ip")

    assert [name for name, _args in orchestrator.tool_broker.calls] == ["network_ip_info"]
    assert "192.168.1.20" in reply
    assert "203.0.113.20" in reply
    assert "IP details yahi hain" in reply
    assert "Nmap" not in reply
    assert "port scan" not in reply


class _FakeIpProcess:
    returncode = 0
    stdout = json.dumps([
        {
            "ifname": "wlan0",
            "operstate": "UP",
            "addr_info": [
                {"family": "inet", "local": "192.168.1.20", "scope": "global"},
                {"family": "inet6", "local": "fe80::1", "scope": "link"},
                {"family": "inet6", "local": "2001:db8::20", "scope": "global"},
            ],
        },
        {
            "ifname": "lo",
            "operstate": "UNKNOWN",
            "addr_info": [{"family": "inet", "local": "127.0.0.1", "scope": "host"}],
        },
    ])


class _FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return b'{"ip":"203.0.113.20"}'


def test_network_ip_info_uses_local_interface_data_and_public_ip_lookup(monkeypatch):
    monkeypatch.setattr(network_info.shutil, "which", lambda name: "/usr/sbin/ip")
    monkeypatch.setattr(network_info.subprocess, "run", lambda *_a, **_kw: _FakeIpProcess())
    monkeypatch.setattr(network_info.urllib.request, "urlopen", lambda *_a, **_kw: _FakeHttpResponse())

    result = network_info.get_network_ip_info()

    assert result["local_ipv4"] == [{"address": "192.168.1.20", "interface": "wlan0"}]
    assert result["local_ipv6"] == [{"address": "2001:db8::20", "interface": "wlan0"}]
    assert result["public_ipv4"] == "203.0.113.20"
    assert result["network_scan_performed"] is False


def test_network_ip_info_handles_public_ip_service_failure(monkeypatch):
    monkeypatch.setattr(network_info.shutil, "which", lambda _name: None)
    monkeypatch.setattr(network_info.socket, "getaddrinfo", lambda *_a, **_kw: [
        (2, 1, 6, "", ("192.168.1.20", 0))
    ])

    def fail_urlopen(*_args, **_kwargs):
        raise TimeoutError("offline")

    monkeypatch.setattr(network_info.urllib.request, "urlopen", fail_urlopen)
    result = network_info.get_network_ip_info()

    assert result["local_ipv4"] == [{"address": "192.168.1.20", "interface": "host-resolution"}]
    assert result["public_ipv4"] is None
    assert result["public_ipv4_status"] == "unavailable (TimeoutError)"
    assert result["network_scan_performed"] is False


def test_planner_does_not_route_plain_ip_check_to_security_agent():
    plan = Planner().plan("check my ip")
    assert plan.agent == "utility"
    assert plan.intent == "network_ip_info"

def test_recent_ip_response_echo_does_not_retrigger_ip_lookup():
    import time
    from jenefar.voice.browser import BrowserVoiceBridge

    orchestrator = SimpleNamespace(
        _is_ip_info_query=JenefarOrchestrator._is_ip_info_query,
    )
    bridge = object.__new__(BrowserVoiceBridge)
    bridge.orchestrator = orchestrator
    bridge._last_assistant_text = (
        "Aapke computer ki IP information: Local IPv4: 192.168.1.20; "
        "Public IPv4: 203.0.113.20"
    )
    bridge._last_assistant_spoken_at = time.monotonic()
    bridge._ip_echo_window = 24.0

    assert bridge._is_recent_assistant_ip_echo("check my ip")
    assert not bridge._is_recent_assistant_ip_echo("scan my network with nmap")

