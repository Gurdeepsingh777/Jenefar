from __future__ import annotations

import shutil
from dataclasses import dataclass

@dataclass(frozen=True)
class DiscoveredTool:
    name: str
    category: str
    command: str
    installed: bool
    description: str

DEFAULT_KALI_TOOLS = (
    ("nmap","recon","Network/service discovery"),
    ("masscan","recon","High-speed port scanner"),
    ("nikto","web","Web server scanner"),
    ("sqlmap","web","SQL injection testing tool"),
    ("ffuf","web","Web fuzzing/content discovery"),
    ("gobuster","web","Content/DNS discovery"),
    ("whatweb","web","Web technology fingerprinting"),
    ("hydra","auth","Network authentication auditing"),
    ("john","password","Password auditing"),
    ("hashcat","password","Password recovery/auditing"),
    ("aircrack-ng","wireless","Wi-Fi security auditing suite"),
    ("wpscan","web","WordPress security scanner"),
    ("searchsploit","research","Exploit-DB search utility"),
    ("enum4linux-ng","enum","SMB/Windows enumeration"),
    ("smbclient","enum","SMB client"),
    ("responder","network","Network protocol analysis/testing"),
    ("burpsuite","web","Web application security testing"),
)

def discover_tools(extra: tuple[str, ...] = ()) -> list[DiscoveredTool]:
    names = list(DEFAULT_KALI_TOOLS)
    names.extend((name, "custom", "User-specified executable") for name in extra)
    return [
        DiscoveredTool(
            name=name,
            category=category,
            command=command,
            installed=shutil.which(command) is not None,
            description=description,
        )
        for name, category, command, description in names
    ]
