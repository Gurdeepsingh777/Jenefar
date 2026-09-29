from __future__ import annotations

from dataclasses import dataclass, field

from jenefar.core.task_plan import HierarchicalTaskPlanner, TaskStep


@dataclass
class Plan:
    intent: str
    agent: str
    needs_tool: bool = False
    confidence: float = 0.5
    reason: str = ""
    steps: list[TaskStep] = field(default_factory=list)

    @property
    def is_compound(self) -> bool:
        return len(self.steps) > 1


class Planner:
    """Deterministic intent planner plus bounded hierarchical decomposition."""

    def __init__(self) -> None:
        self.task_planner = HierarchicalTaskPlanner()

    def _make_plan(
        self,
        text: str,
        intent: str,
        agent: str,
        *,
        needs_tool: bool = False,
        confidence: float,
        reason: str,
    ) -> Plan:
        task_plan = self.task_planner.build(text, intent, agent)
        return Plan(
            intent=intent,
            agent=agent,
            needs_tool=needs_tool,
            confidence=confidence,
            reason=reason,
            steps=list(task_plan.steps),
        )

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
        if "kali" in t or any(x in t for x in ("nmap", "hashcat", "metasploit", "burpsuite", "sqlmap")):
            return self._make_plan(text, "kali", "kali", confidence=0.96, reason="Kali/security-tool keyword match", needs_tool=True)

        if any(x in t for x in (
            "find on screen", "locate on screen", "click the", "click on",
            "press the button", "find the button", "search box", "address bar",
            "what is on my screen", "semantic gui", "semantic click",
        )):
            return self._make_plan(
                text,
                "semantic_gui",
                "gui_vision",
                confidence=0.97,
                reason="semantic GUI/vision keyword match",
                needs_tool=True,
            )

        if any(x in t for x in ("youtube", "song", "mp3", "vlc", "browser", "music")):
            return self._make_plan(text, "media_automation", "automation", confidence=0.95, reason="browser/media automation keyword match", needs_tool=True)

        if any(x in t for x in (
            ".py", "python file", "python script", "fix error", "edit file",
            "modify file", "add a feature", "custom feature", "run this file",
            "check this file",
        )):
            return self._make_plan(text, "local_development", "local_development", confidence=0.96, reason="local code/file task keyword match", needs_tool=True)

        if any(x in t for x in repository_terms):
            return self._make_plan(text, "repository", "repository", confidence=0.95, reason="repository/GitHub keyword match", needs_tool=True)

        if any(x in t for x in ("desktop", "screen", "screenshot", "mouse", "keyboard", "click", "gui", "window")):
            return self._make_plan(text, "automation", "automation", confidence=0.94, reason="desktop automation keyword match", needs_tool=True)

        if any(x in t for x in ("python", "pip", "pytest", "django", "fastapi", "flask")):
            return self._make_plan(text, "coding", "python", confidence=0.95, reason="python keyword match")

        if any(x in t for x in ("bug bounty", "bugbounty", "xss", "sqli", "idor", "burp")):
            return self._make_plan(text, "bugbounty", "bugbounty", confidence=0.92, reason="application-security keyword match")

        if any(x in t for x in ("robot", "arduino", "esp32", "ros", "servo", "sensor", "motor")):
            return self._make_plan(text, "robotics", "robotics", confidence=0.92, reason="robotics keyword match")

        if any(x in t for x in ("kali", "nmap", "cve", "malware", "cybersecurity", "network")):
            return self._make_plan(text, "cybersecurity", "cybersecurity", confidence=0.9, reason="security keyword match")

        return self._make_plan(text, "research", "research", confidence=0.55, reason="fallback")
