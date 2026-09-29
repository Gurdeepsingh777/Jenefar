from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Plan:
    intent: str
    agent: str
    needs_tool: bool = False
    reason: str = ""

class Planner:
    def plan(self, text: str) -> Plan:
        t=text.lower()
        if any(x in t for x in ("python","pip","pytest","django","fastapi","flask")):
            return Plan("coding","python",reason="python keyword match")
        if any(x in t for x in ("bug bounty","xss","sqli","idor","burp")):
            return Plan("bugbounty","bugbounty",reason="application-security keyword match")
        if any(x in t for x in ("robot","arduino","esp32","ros","servo","sensor","motor")):
            return Plan("robotics","robotics",reason="robotics keyword match")
        if any(x in t for x in ("kali","nmap","cve","malware","cybersecurity","network")):
            return Plan("cybersecurity","cybersecurity",reason="security keyword match")
        return Plan("research","research",reason="fallback")
