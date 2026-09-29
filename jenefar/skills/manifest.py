from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class SkillManifest:
    name: str
    version: str
    description: str
    keywords: tuple[str, ...] = ()
    connectors: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    system_prompt: str = ""
    source: str = "builtin"
    enabled_by_default: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "keywords": list(self.keywords),
            "connectors": list(self.connectors),
            "permissions": list(self.permissions),
            "system_prompt": self.system_prompt,
            "source": self.source,
            "enabled_by_default": self.enabled_by_default,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, source: str = "file") -> "SkillManifest":
        if not isinstance(raw, dict):
            raise ValueError("Skill manifest must be a JSON object.")

        name = " ".join(str(raw.get("name", "")).split()).strip().lower()
        version = " ".join(str(raw.get("version", "1.0")).split()).strip()
        description = " ".join(str(raw.get("description", "")).split()).strip()
        if not name:
            raise ValueError("Skill manifest requires a non-empty name.")
        if not description:
            raise ValueError("Skill manifest requires a non-empty description.")

        def tuple_strings(value: Any, field_name: str) -> tuple[str, ...]:
            if value is None:
                return ()
            if not isinstance(value, list):
                raise ValueError(f"Skill manifest field '{field_name}' must be a list.")
            return tuple(
                cleaned
                for item in value
                if (cleaned := " ".join(str(item).split()).strip())
            )

        keywords = tuple_strings(raw.get("keywords"), "keywords")
        connectors = tuple_strings(raw.get("connectors"), "connectors")
        permissions = tuple_strings(raw.get("permissions"), "permissions")
        prompt = str(raw.get("system_prompt", "") or "").strip()
        enabled = bool(raw.get("enabled_by_default", True))

        if len(name) > 100 or len(description) > 1000 or len(prompt) > 6000:
            raise ValueError("Skill manifest metadata exceeds configured size limits.")

        return cls(
            name=name,
            version=version or "1.0",
            description=description,
            keywords=keywords[:50],
            connectors=connectors[:50],
            permissions=permissions[:50],
            system_prompt=prompt,
            source=source,
            enabled_by_default=enabled,
        )


def load_manifest(path: str | Path) -> SkillManifest:
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)

    suffix = candidate.suffix.lower()
    if suffix not in {".json", ".skill"}:
        raise ValueError("Skill manifests must be .json or .skill files.")

    raw = json.loads(candidate.read_text(encoding="utf-8"))
    return SkillManifest.from_dict(raw, source=str(candidate))


BUILTIN_SKILLS = (
    SkillManifest(
        name="local_development",
        version="1.0",
        description="Authorized local Python/file inspection, repair and test workflow.",
        keywords=("python script", ".py", "fix error", "edit file", "run this file"),
        connectors=("workspace",),
        permissions=("workspace_read", "workspace_edit", "python_execute"),
    ),
    SkillManifest(
        name="gui_vision",
        version="1.0",
        description="Vision-backed semantic screen understanding and GUI control.",
        keywords=("screen", "button", "search box", "address bar", "click on"),
        connectors=("desktop",),
        permissions=("screen_capture", "gui_action"),
    ),
    SkillManifest(
        name="browser_media",
        version="1.0",
        description="Browser and local media playback automation.",
        keywords=("youtube", "browser", "song", "mp3", "vlc", "music"),
        connectors=("browser", "media"),
        permissions=("browser_open", "media_play"),
    ),
    SkillManifest(
        name="github_research",
        version="1.0",
        description="Public GitHub repository research and read-only analysis.",
        keywords=("github", "repository", "repo", "codebase"),
        connectors=("github",),
        permissions=("public_network_read",),
    ),
    SkillManifest(
        name="robotics",
        version="1.0",
        description="Serial, MQTT and ROS2 robotics interaction.",
        keywords=("robot", "esp32", "arduino", "ros2", "mqtt", "servo", "motor"),
        connectors=("robotics",),
        permissions=("robot_read", "robot_action"),
    ),
    SkillManifest(
        name="security",
        version="1.0",
        description="Scoped cybersecurity and Kali workflows.",
        keywords=("kali", "nmap", "burpsuite", "sqlmap", "hashcat"),
        connectors=("security",),
        permissions=("authorized_security_action",),
    ),
    SkillManifest(
        name="research",
        version="1.0",
        description="Public web/document research and evidence synthesis.",
        keywords=("research", "search", "look up", "documentation"),
        connectors=("web", "github"),
        permissions=("public_network_read",),
    ),
)


__all__ = ["SkillManifest", "BUILTIN_SKILLS", "load_manifest"]
