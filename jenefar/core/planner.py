from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Plan:
    intent: str
    agent: str
    needs_tool: bool = False
    confidence: float = 0.5
    reason: str = ""


class Planner:
    """Small deterministic intent planner used as the first routing signal."""

    def plan(self, text: str) -> Plan:
        t = text.lower()

        repository_terms = (
            "github",
            "repository",
            "repo",
            "pull request",
            "pull-request",
            "codebase",
            "architecture review",
        )
        if any(x in t for x in repository_terms):
            return Plan(
                "repository",
                "repository",
                confidence=0.95,
                reason="repository/GitHub keyword match",
            )

        if any(x in t for x in ("desktop", "screen", "screenshot", "mouse", "keyboard", "click", "gui", "window")):
            return Plan(
                "automation",
                "automation",
                confidence=0.94,
                reason="desktop automation keyword match",
            )

        if any(x in t for x in ("python", "pip", "pytest", "django", "fastapi", "flask")):
            return Plan(
                "coding",
                "python",
                confidence=0.95,
                reason="python keyword match",
            )

        if any(x in t for x in ("bug bounty", "bugbounty", "xss", "sqli", "idor", "burp")):
            return Plan(
                "bugbounty",
                "bugbounty",
                confidence=0.92,
                reason="application-security keyword match",
            )

        if any(x in t for x in ("robot", "arduino", "esp32", "ros", "servo", "sensor", "motor")):
            return Plan(
                "robotics",
                "robotics",
                confidence=0.92,
                reason="robotics keyword match",
            )

        if any(x in t for x in ("kali", "nmap", "cve", "malware", "cybersecurity", "network")):
            return Plan(
                "cybersecurity",
                "cybersecurity",
                confidence=0.9,
                reason="security keyword match",
            )

        return Plan(
            "research",
            "research",
            confidence=0.55,
            reason="fallback",
        )
