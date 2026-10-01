from __future__ import annotations

from dataclasses import dataclass, field

from jenefar.core.task_plan import HierarchicalTaskPlanner, TaskStep
from jenefar.skills.manager import SkillManager


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

    def __init__(self, skills: SkillManager | None = None) -> None:
        self.task_planner = HierarchicalTaskPlanner()
        self.skills = skills or SkillManager()

    def skill_enabled(self, skill_name: str) -> bool:
        return self.skills.is_enabled(skill_name)

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
        skill_for_agent = {
            "local_development": "local_development",
            "python": "local_development",
            "repository": "github_research",
            "gui_vision": "gui_vision",
            "automation": "browser_media",
            "kali": "security",
            "cybersecurity": "security",
            "bugbounty": "security",
            "robotics": "robotics",
            "research": "research",
        }.get(agent)
        if skill_for_agent and not self.skills.is_enabled(skill_for_agent):
            disabled_reason = f"required skill '{skill_for_agent}' is disabled"
            if agent != "research" and self.skills.is_enabled("research"):
                return self._make_plan(
                    text,
                    "research",
                    "research",
                    confidence=0.4,
                    reason=disabled_reason,
                )
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
            "screen par", "screen pe", "screen kya", "screen read",
            "live screen", "my screen", "meri screen", "mere screen",
            "screen dekho", "screen dikh", "screen me kya",
        )):
            return self._make_plan(
                text,
                "semantic_gui",
                "gui_vision",
                confidence=0.97,
                reason="semantic GUI/vision keyword match",
                needs_tool=True,
            )

        if any(x in t for x in ("time", "current time", "what time", "date today", "today's date", "clock")):
            return self._make_plan(text, "utility", "utility", confidence=0.98, reason="local time/date utility keyword match", needs_tool=True)

        if any(x in t for x in (
            "remember", "save in memory", "store in memory", "recall from memory",
            "procedure", "playbook", "schedule", "remind me", "every day",
            "every hour", "every week", "watch for", "when this happens",
            "trigger an event", "event watcher",
        )):
            return self._make_plan(
                text,
                "utility",
                "utility",
                confidence=0.97,
                reason="persistent memory/scheduler keyword match",
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
