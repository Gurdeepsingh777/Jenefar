import json

from jenefar.agents.cybersecurity.kali import KaliSecurityAgent
from jenefar.core.agent import AgentContext


class FakeBroker:
    def __init__(self):
        self.calls = []

    def invoke(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "kali_catalog":
            return json.dumps({
                "status": "ok",
                "result": [
                    {
                        "name": "nmap",
                        "category": "information-gathering",
                        "tactic": "Discovery",
                        "path": "/usr/bin/nmap",
                        "source": "curated",
                        "installed": True,
                    },
                    {
                        "name": "arp-scan",
                        "category": "network",
                        "tactic": "Discovery",
                        "path": "/usr/sbin/arp-scan",
                        "source": "path-discovered",
                        "installed": True,
                    },
                ],
            })
        if name == "kali_tool_help":
            return json.dumps({
                "status": "ok",
                "result": {
                    "tool": "arp-scan",
                    "installed": True,
                    "path": "/usr/sbin/arp-scan",
                    "source": "--help output",
                    "help": "Usage: arp-scan [options] [hosts...]\n--interface=IFACE  use a network interface",
                    "inspected_for_this_session": True,
                    "inspection_note": "Local help/manual was read.",
                },
            })
        raise AssertionError(f"Unexpected tool call: {name}")


def test_explicit_kali_discovery_uses_live_catalog_and_help_without_scanning():
    broker = FakeBroker()
    agent = KaliSecurityAgent(tool_broker=broker)
    task = (
        "Mere Kali Linux ke network scanning tools discover karo. "
        "kali_catalog se installed tools search karo, phir kisi unfamiliar tool ko "
        "kali_tool_help se inspect karo. Execution se pehle authorized target ka "
        "scope check karo aur mujhe exact command aur expected result dikhao. "
        "Meri approval ke bina koi scan ya high-impact command execute mat karna."
    )

    result = agent.run(AgentContext(task=task))

    assert [name for name, _ in broker.calls] == ["kali_catalog", "kali_tool_help"]
    assert broker.calls[0][1]["query"] == "network scanning tools"
    assert broker.calls[1][1]["tool"] == "arp-scan"
    assert "arp-scan" in result.content
    assert "Usage: arp-scan" in result.content
    assert "No network scan or high-impact command was executed." in result.content
    assert "192.168.29.0/24" not in result.content
    assert result.metadata["scan_executed"] is False


def test_discovery_guard_does_not_intercept_explicit_target_scan_request():
    task = "Discover Kali network scanning tools and run scan against 192.168.29.10"
    assert KaliSecurityAgent._is_tool_catalog_request(task) is False
