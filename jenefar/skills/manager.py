from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from jenefar.skills.manifest import BUILTIN_SKILLS, SkillManifest, load_manifest

ROOT = Path(__file__).resolve().parents[2]


class SkillManager:
    """Persistent, declarative skill registry.

    Skills are metadata/prompt/connector declarations. They do not execute
    arbitrary installed code. Executable behavior comes from registered
    connectors and the central tool broker.
    """

    def __init__(
        self,
        state_path: str | Path = "data/skills.json",
        skill_roots: list[str | Path] | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        configured_roots = os.getenv("JENEFAR_SKILL_ROOTS", "")
        env_roots = [
            item.strip()
            for item in configured_roots.split(os.pathsep)
            if item.strip()
        ]
        self.skill_roots = [
            Path(item).expanduser().resolve()
            for item in (skill_roots or env_roots)
        ]
        if not self.skill_roots:
            self.skill_roots = [ROOT / "skills"]
        self._lock = threading.Lock()
        self._skills: dict[str, SkillManifest] = {
            skill.name: skill for skill in BUILTIN_SKILLS
        }
        self._load_installed()
        self._load_state()

    def _load_installed(self) -> None:
        for root in self.skill_roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.json")):
                try:
                    manifest = load_manifest(path)
                    self._skills[manifest.name] = manifest
                except Exception:
                    continue

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"enabled": [skill.name for skill in BUILTIN_SKILLS if skill.enabled_by_default]}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _write_state(self, enabled: set[str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"enabled": sorted(enabled)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _enabled_names(self) -> set[str]:
        state = self._load_state()
        names = state.get("enabled")
        if not isinstance(names, list):
            names = [skill.name for skill in BUILTIN_SKILLS if skill.enabled_by_default]
        return {str(item).strip().lower() for item in names if str(item).strip()}

    def list(self) -> list[dict[str, Any]]:
        enabled = self._enabled_names()
        return [
            {
                **skill.as_dict(),
                "enabled": skill.name in enabled,
                "available": True,
            }
            for skill in sorted(self._skills.values(), key=lambda item: item.name)
        ]

    def get(self, name: str) -> SkillManifest:
        key = str(name).strip().lower()
        try:
            return self._skills[key]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {key}") from exc

    def is_enabled(self, name: str) -> bool:
        key = str(name).strip().lower()
        return key in self._enabled_names() and key in self._skills

    def enable(self, name: str) -> dict[str, Any]:
        skill = self.get(name)
        with self._lock:
            enabled = self._enabled_names()
            enabled.add(skill.name)
            self._write_state(enabled)
        return {"skill": skill.name, "enabled": True}

    def disable(self, name: str) -> dict[str, Any]:
        skill = self.get(name)
        with self._lock:
            enabled = self._enabled_names()
            enabled.discard(skill.name)
            self._write_state(enabled)
        return {"skill": skill.name, "enabled": False}

    def install_manifest(self, path: str) -> dict[str, Any]:
        candidate = Path(path).expanduser().resolve()
        allowed = any(root == candidate.parent or root in candidate.parents for root in self.skill_roots)
        if not allowed:
            raise PermissionError(
                "Skill manifest is outside configured JENEFAR_SKILL_ROOTS."
            )
        manifest = load_manifest(candidate)
        self._skills[manifest.name] = manifest
        if manifest.enabled_by_default:
            self.enable(manifest.name)
        return {
            "installed": True,
            "skill": manifest.as_dict(),
        }

    def prompt_context(self) -> str:
        enabled = [
            self.get(item["name"])
            for item in self.list()
            if item["enabled"]
        ]
        lines = [
            f"- {item.name}: {item.description}"
            for item in enabled
        ]
        return "\n".join(lines)

    def connectors_for(self, name: str) -> list[str]:
        return list(self.get(name).connectors)


__all__ = ["SkillManager"]
