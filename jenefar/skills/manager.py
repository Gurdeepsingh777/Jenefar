from __future__ import annotations

import json
import os
import re
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
        repo_roots = []
        if str(os.getenv("JENEFAR_REA_SKILL_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}:
            # REA's official reverse-engineering workflow is prompt-only guidance.
            # Its MCP server is registered separately by the REA connector.
            repo_roots.append(ROOT / "skills" / "rea")
        self.skill_roots = [
            Path(item).expanduser().resolve()
            for item in (skill_roots or env_roots)
        ]
        if not self.skill_roots:
            self.skill_roots = [ROOT / "skills"]
        for root in repo_roots:
            resolved = root.resolve()
            if resolved not in self.skill_roots:
                self.skill_roots.append(resolved)
        self._lock = threading.Lock()
        self._skills: dict[str, SkillManifest] = {
            skill.name: skill for skill in BUILTIN_SKILLS
        }
        self._discovered_paths: set[Path] = set()
        self._load_state()
        self._load_installed(auto_enable_new=True)

    def _load_installed(self, *, auto_enable_new: bool = False) -> None:
        """Discover declarative manifests only within configured local skill roots.

        Supports flat JSON/.skill manifests and Hermes-style child-folder SKILL.md
        files. Skill instructions are prompt text only; no supplied code is executed.
        """
        discovered: list[tuple[Path, SkillManifest]] = []
        for root_value in self.skill_roots:
            root = root_value.resolve()
            if not root.is_dir():
                continue
            candidates = list(root.glob("*.json")) + list(root.glob("*.skill"))
            candidates += list(root.glob("*/SKILL.md"))
            for path in sorted(set(candidates)):
                try:
                    resolved = path.resolve()
                    if root != resolved and root not in resolved.parents:
                        continue
                    if path.name.lower() == "skill.md":
                        source = path.read_text(encoding="utf-8")
                        if len(source) > 24000 or not source.lstrip().startswith("---"):
                            continue
                        parts = source.lstrip().split("---", 2)
                        if len(parts) != 3:
                            continue
                        import yaml
                        metadata = yaml.safe_load(parts[1]) or {}
                        if not isinstance(metadata, dict):
                            continue
                        metadata = dict(metadata)
                        metadata["system_prompt"] = parts[2].strip()[:6000]
                        metadata.setdefault("name", path.parent.name)
                        metadata.setdefault("description", "Local declarative Hermes-style skill.")
                        manifest = SkillManifest.from_dict(metadata, source=str(path))
                    else:
                        manifest = load_manifest(path)
                    discovered.append((resolved, manifest))
                except Exception:
                    continue
        known_names = set(self._skills)
        for path, manifest in discovered:
            self._skills[manifest.name] = manifest
            self._discovered_paths.add(path)
        if auto_enable_new and discovered:
            enabled = self._enabled_names()
            changed = False
            for _path, manifest in discovered:
                if manifest.name not in known_names and manifest.enabled_by_default:
                    enabled.add(manifest.name)
                    changed = True
            if changed:
                self._write_state(enabled)

    def refresh(self) -> dict[str, Any]:
        """Rescan configured roots so newly-added skill files load without restart."""
        before = set(self._skills)
        self._load_installed(auto_enable_new=True)
        return {"discovered": sorted(set(self._skills) - before), "count": len(self._skills)}

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"enabled": [skill.name for skill in self._skills.values() if skill.enabled_by_default]}
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
            names = [skill.name for skill in self._skills.values() if skill.enabled_by_default]
        return {str(item).strip().lower() for item in names if str(item).strip()}

    def list(self) -> list[dict[str, Any]]:
        self._load_installed(auto_enable_new=True)
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
        self._load_installed(auto_enable_new=True)
        key = str(name).strip().lower()
        try:
            return self._skills[key]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {key}") from exc

    def is_enabled(self, name: str) -> bool:
        self._load_installed(auto_enable_new=True)
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

    def save_learned_skill(
        self,
        *,
        name: str,
        description: str,
        keywords: list[str],
        system_prompt: str,
        connectors: list[str] | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist a learned, declarative skill; never install or execute code."""
        raw = {
            "name": name,
            "version": "1.0",
            "description": description,
            "keywords": keywords,
            "connectors": connectors or [],
            "permissions": permissions or [],
            "system_prompt": system_prompt,
            "enabled_by_default": True,
        }
        manifest = SkillManifest.from_dict(raw, source="learned")
        builtin_names = {item.name for item in BUILTIN_SKILLS}
        if manifest.name in builtin_names:
            raise ValueError("A learned skill cannot overwrite a built-in skill.")
        if not manifest.keywords:
            raise ValueError("A learned skill needs at least one keyword for automatic matching.")
        if not manifest.system_prompt:
            raise ValueError("A learned skill needs reusable guidance in system_prompt.")

        slug = re.sub(r"[^a-z0-9]+", "-", manifest.name.lower()).strip("-")[:80]
        if not slug:
            raise ValueError("Skill name does not produce a valid folder name.")
        root = self.skill_roots[0].resolve()
        root.mkdir(parents=True, exist_ok=True)
        skill_dir = (root / slug).resolve()
        try:
            skill_dir.relative_to(root)
        except ValueError as exc:
            raise PermissionError("Skill destination escaped the configured skill root.") from exc

        skill_dir.mkdir(parents=True, exist_ok=True)
        target = (skill_dir / "SKILL.md").resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise PermissionError("Skill file escaped the configured skill root.") from exc

        import yaml

        front_matter = {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "keywords": list(manifest.keywords),
            "connectors": list(manifest.connectors),
            "permissions": list(manifest.permissions),
            "enabled_by_default": True,
        }
        encoded = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True)
        target.write_text(
            "---\n" + encoded + "---\n" + manifest.system_prompt.strip() + "\n",
            encoding="utf-8",
        )

        # Reload through the same bounded declarative parser used at startup,
        # then enable it in persistent skills state.
        self._load_installed(auto_enable_new=True)
        self.enable(manifest.name)
        return {
            "saved": True,
            "enabled": True,
            "name": manifest.name,
            "path": str(target),
            "executable_code_installed": False,
        }

    def connectors_for(self, name: str) -> list[str]:
        return list(self.get(name).connectors)


__all__ = ["SkillManager"]
