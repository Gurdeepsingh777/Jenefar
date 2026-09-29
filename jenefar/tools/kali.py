from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from jenefar.execution.scope import ScopePolicy


@dataclass(frozen=True)
class KaliToolInfo:
    name: str
    tactic: str
    category: str
    description: str


COMMON = (
    KaliToolInfo("nmap", "Discovery", "information-gathering", "Network and service discovery"),
    KaliToolInfo("masscan", "Discovery", "information-gathering", "High-speed port discovery"),
    KaliToolInfo("rustscan", "Discovery", "information-gathering", "Port scanning and discovery"),
    KaliToolInfo("amass", "Reconnaissance", "information-gathering", "Attack-surface discovery and enumeration"),
    KaliToolInfo("subfinder", "Reconnaissance", "information-gathering", "Passive subdomain discovery"),
    KaliToolInfo("theHarvester", "Reconnaissance", "information-gathering", "OSINT collection"),
    KaliToolInfo("spiderfoot", "Reconnaissance", "information-gathering", "OSINT automation"),
    KaliToolInfo("whatweb", "Discovery", "web", "Web technology fingerprinting"),
    KaliToolInfo("nikto", "Discovery", "web", "Web-server assessment"),
    KaliToolInfo("ffuf", "Discovery", "web", "Web content discovery/fuzzing"),
    KaliToolInfo("gobuster", "Discovery", "web", "Directory/DNS/VHost discovery"),
    KaliToolInfo("feroxbuster", "Discovery", "web", "Web content discovery"),
    KaliToolInfo("burpsuite", "Initial Access", "web", "Web application security testing"),
    KaliToolInfo("zaproxy", "Initial Access", "web", "Web application security testing"),
    KaliToolInfo("sqlmap", "Initial Access", "web", "SQL injection testing"),
    KaliToolInfo("hydra", "Credential Access", "passwords", "Authentication auditing"),
    KaliToolInfo("john", "Credential Access", "passwords", "Password auditing/recovery"),
    KaliToolInfo("hashcat", "Credential Access", "passwords", "Password recovery/auditing"),
    KaliToolInfo("aircrack-ng", "Credential Access", "wireless", "Wi-Fi security auditing suite"),
    KaliToolInfo("enum4linux-ng", "Discovery", "windows", "Windows/SMB enumeration"),
    KaliToolInfo("netexec", "Lateral Movement", "windows", "Windows network administration/security testing"),
    KaliToolInfo("impacket-secretsdump", "Credential Access", "windows", "Credential extraction/testing"),
    KaliToolInfo("responder", "Credential Access", "sniffing-spoofing", "Network protocol authentication testing"),
    KaliToolInfo("metasploit", "Execution", "exploitation", "Authorized exploit/lab framework"),
    KaliToolInfo("msfconsole", "Execution", "exploitation", "Metasploit console"),
    KaliToolInfo("msfvenom", "Resource Development", "exploitation", "Payload generation utility"),
    KaliToolInfo("evil-winrm", "Lateral Movement", "windows", "Windows remote management testing"),
    KaliToolInfo("bloodhound", "Discovery", "windows", "Active Directory relationship discovery"),
    KaliToolInfo("mimikatz", "Credential Access", "post-exploitation", "Credential security testing"),
    KaliToolInfo("linpeas", "Privilege Escalation", "post-exploitation", "Local privilege-escalation enumeration"),
    KaliToolInfo("winpeas", "Privilege Escalation", "post-exploitation", "Windows privilege-escalation enumeration"),
    KaliToolInfo("socat", "Command and Control", "network", "Network relay utility"),
    KaliToolInfo("nc", "Command and Control", "network", "Network connection utility"),
    KaliToolInfo("wireshark", "Collection", "sniffing-spoofing", "Packet capture/analysis"),
    KaliToolInfo("tcpdump", "Collection", "sniffing-spoofing", "Packet capture"),
    KaliToolInfo("foremost", "Forensics", "forensics", "File carving"),
    KaliToolInfo("binwalk", "Forensics", "forensics", "Firmware/file analysis"),
    KaliToolInfo("volatility3", "Forensics", "forensics", "Memory forensics"),
)


class KaliToolManager:
    """Discovery + tightly scoped execution of installed Kali tools."""

    def __init__(self, scope: ScopePolicy | None = None) -> None:
        self.scope = scope or ScopePolicy()
        self.catalog = {item.name: item for item in COMMON}

    def catalog_list(self, category: str | None = None, tactic: str | None = None) -> list[dict[str, Any]]:
        items = []
        for item in self.catalog.values():
            if category and item.category != category:
                continue
            if tactic and item.tactic.lower() != tactic.lower():
                continue
            items.append({
                "name": item.name,
                "tactic": item.tactic,
                "category": item.category,
                "installed": shutil.which(item.name) is not None,
                "description": item.description,
            })
        return items

    def execute(self, *, tool: str, args: list[str], target: str = "", timeout: int = 120) -> dict[str, Any]:
        info = self.catalog.get(tool)
        if info is None:
            raise ValueError(
                f"Kali tool '{tool}' is not in the curated catalog. Use discover_kali_tools first."
            )

        executable = shutil.which(tool)
        if not executable:
            raise FileNotFoundError(f"Kali tool '{tool}' is not installed.")

        if target and not self.scope.allows(target):
            raise PermissionError(
                f"Target '{target}' is outside configured authorized_targets."
            )

        command = [executable, *[str(arg) for arg in args]]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 300)),
        )
        return {
            "tool": tool,
            "tactic": info.tactic,
            "category": info.category,
            "target": target,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-20000:],
            "stderr": completed.stderr[-20000:],
        }
