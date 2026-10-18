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

def test_browser_audio_is_rejected_as_busy_before_stt_when_task_is_running():
    from jenefar.voice.browser import BrowserVoiceBridge

    class RunningTask:
        def done(self):
            return False

    bridge = object.__new__(BrowserVoiceBridge)
    bridge._active_task = RunningTask()

    result = bridge.handle_audio(b"not-needing-decode", "audio/webm")

    assert result["busy"] is True
    assert result["reason"] == "assistant_busy"
    assert result["accepted"] is False

def test_browser_audio_is_discarded_if_another_task_starts_during_stt(monkeypatch):
    from jenefar.voice.browser import BrowserVoiceBridge
    import subprocess
    import shutil

    class FakeProcess:
        returncode = 0
        stdout = b"\\x00" * 3200
        stderr = b""

    class FakeStt:
        async def transcribe_pcm(self, _pcm):
            bridge._task_generation += 1
            return "check my ip"

    bridge = object.__new__(BrowserVoiceBridge)
    bridge._active_task = None
    bridge._task_generation = 0
    bridge._stt_runtime = FakeStt()
    bridge._last_assistant_spoken_at = 0.0
    bridge._last_assistant_text = ""
    bridge._ip_echo_window = 24.0
    bridge.orchestrator = SimpleNamespace(
        _is_ip_info_query=JenefarOrchestrator._is_ip_info_query,
    )
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: FakeProcess())

    result = bridge.handle_audio(b"fake-audio", "audio/webm")

    assert result["busy"] is True
    assert result["reason"] == "task_started_during_transcription"
    assert result["accepted"] is False

def test_host_discovery_request_is_not_misclassified_as_ip_information():
    request = "meri ip ki range ko select kro or check kro ki kitne host online h"

    assert JenefarOrchestrator._is_local_host_discovery_request(request)
    assert not JenefarOrchestrator._is_ip_info_query(request)

    plan = Planner().plan(request)
    assert plan.intent == "network_host_discovery"
    assert plan.agent == "kali"


def test_primary_private_ipv4_network_prefers_default_lan_and_ignores_docker(monkeypatch):
    links = [
        {
            "ifname": "wlan0",
            "operstate": "UP",
            "addr_info": [{
                "family": "inet", "local": "192.168.29.165",
                "prefixlen": 24, "scope": "global",
            }],
        },
        {
            "ifname": "docker0",
            "operstate": "UP",
            "addr_info": [{
                "family": "inet", "local": "172.17.0.1",
                "prefixlen": 16, "scope": "global",
            }],
        },
        {
            "ifname": "br-a2502a6c2ddb",
            "operstate": "UP",
            "addr_info": [{
                "family": "inet", "local": "172.18.0.1",
                "prefixlen": 16, "scope": "global",
            }],
        },
    ]

    class Result:
        returncode = 0
        stdout = ""

    def fake_run(command, **_kwargs):
        result = Result()
        if command[1:4] == ["-j", "address", "show"]:
            result.stdout = json.dumps(links)
        elif command[1:4] == ["-4", "route", "show"]:
            result.stdout = "default via 192.168.29.1 dev wlan0 proto dhcp metric 600"
        else:
            result.returncode = 1
        return result

    monkeypatch.setattr(network_info.shutil, "which", lambda _name: "/usr/sbin/ip")
    monkeypatch.setattr(network_info.subprocess, "run", fake_run)

    result = network_info.get_primary_private_ipv4_network()

    assert result["status"] == "ok"
    assert result["interface"] == "wlan0"
    assert result["address"] == "192.168.29.165"
    assert result["network"] == "192.168.29.0/24"
    assert result["num_addresses"] == 256


def test_host_discovery_request_creates_an_approval_gated_plan(monkeypatch):
    from jenefar.core.state import JenefarState

    request = "meri ip ki range ko select kro or check kro ki kitne host online h"
    network_info_result = {
        "status": "ok",
        "interface": "wlan0",
        "address": "192.168.29.165",
        "network": "192.168.29.0/24",
        "num_addresses": 256,
        "prefixlen": 24,
    }

    class FakeHostBroker:
        def __init__(self):
            self.calls = []

        def invoke(self, name, arguments):
            self.calls.append((name, arguments))
            return json.dumps({
                "status": "approval_required",
                "pending_id": "a" * 32,
                "tool": "kali_tool_execute",
                "user_prompt": (
                    "Purpose/plan: host discovery only\\nCommand: nmap -sn -n -T3 "
                    "192.168.29.0/24\\nTarget(s): 192.168.29.0/24\\n"
                    "Authorization scope: PASS\\nExecute? ["
                    + "a" * 32
                    + "]"
                ),
            })

    orchestrator = object.__new__(JenefarOrchestrator)
    orchestrator.pending_approval_workflows = {}
    orchestrator.session = _FakeSession()
    orchestrator.memory_engine = _FakeMemory()
    orchestrator.graph = _FakeGraph()
    orchestrator.state = None
    orchestrator.config = SimpleNamespace(single_turn_sleep=False)
    orchestrator.tool_broker = FakeHostBroker()
    orchestrator._avatar_state = lambda *_args, **_kwargs: None
    orchestrator._direct_window_transfer = lambda _text: None
    orchestrator._direct_screen_read = lambda _text: None

    monkeypatch.setattr(
        network_info,
        "get_primary_private_ipv4_network",
        lambda: network_info_result,
    )

    reply = orchestrator.handle(request)

    assert len(orchestrator.tool_broker.calls) == 1
    name, arguments = orchestrator.tool_broker.calls[0]
    assert name == "kali_tool_execute"
    assert arguments["tool"] == "nmap"
    assert arguments["args"] == ["-sn", "-n", "-T3", "--max-retries", "1", "192.168.29.0/24"]
    assert arguments["target"] == "192.168.29.0/24"
    assert orchestrator.state == JenefarState.WAITING_APPROVAL
    assert "Selected range: 192.168.29.0/24 via wlan0" in reply
    assert "approval" in reply.lower()
    assert "a" * 32 in reply
    workflow = orchestrator.pending_approval_workflows["a" * 32]
    assert workflow["direct_workflow"] == "local_host_discovery"


def test_nmap_host_discovery_summary_uses_real_reported_count():
    raw = json.dumps({
        "status": "ok",
        "result": {
            "tool": "nmap",
            "returncode": 0,
            "stdout": (
                "Starting Nmap 7.95\\n"
                "Nmap scan report for 192.168.29.1\\n"
                "Host is up (0.001s latency).\\n"
                "Nmap scan report for 192.168.29.165\\n"
                "Host is up.\\n"
                "Nmap done: 256 IP addresses (2 hosts up) scanned in 2.51 seconds\\n"
            ),
            "stderr": "",
        },
    })

    reply = JenefarOrchestrator._summarize_local_host_discovery(
        raw, "192.168.29.0/24"
    )

    assert "2 host(s) online" in reply
    assert "256 addresses checked" in reply
    assert "192.168.29.1" in reply
    assert "192.168.29.165" in reply
    assert "ports aur services scan nahi kiye gaye" in reply

