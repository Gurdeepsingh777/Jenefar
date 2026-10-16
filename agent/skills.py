from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"[a-z0-9_.+-]{3,}")
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:password|passcode|api[_ -]?key|client[_ -]?secret|access[_ -]?token|private[_ -]?key)\b\s*[:=]\s*\S+"
)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")

_STOPWORDS = {
    "please", "make", "create", "help", "with", "from", "this", "that",
    "what", "when", "where", "your", "my", "meri", "mujhe", "karo",
    "karna", "kar", "do", "and", "the", "for", "into", "using", "use",
    "jenefar", "can", "you", "task", "work", "need", "want", "check",
    "tell", "me", "run", "then", "please", "should", "after", "before",
}


class SkillStore:
    """Persistent, prompt-only skill storage using safe YAML front matter in SKILL.md."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def _path_for(self, name: str) -> tuple[str, Path]:
        slug = _SLUG_RE.sub("-", str(name or "").strip().lower()).strip("-")[:72]
        if not slug:
            raise ValueError("Skill name must contain letters or numbers.")
        self.root.mkdir(parents=True, exist_ok=True)
        path = (self.root / slug / "SKILL.md").resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Skill destination escaped the configured skill root.") from exc
        return slug.replace("-", "_"), path

    @staticmethod
    def _validate_text(name: str, description: str, keywords: list[str], instructions: str) -> None:
        combined = "\n".join((name, description, " ".join(keywords), instructions))
        if len(description) > 1000 or len(instructions) > 6000:
            raise ValueError("Skill description is limited to 1 KB and instructions to 6 KB.")
        if not instructions.strip():
            raise ValueError("Skill instructions must not be empty.")
        if len(keywords) > 30 or not keywords:
            raise ValueError("Provide between 1 and 30 skill keywords.")
        if _SENSITIVE_ASSIGNMENT_RE.search(combined):
            raise ValueError("Skill text appears to contain a credential assignment; do not save secrets.")
        if "-----begin private key-----" in combined.lower():
            raise ValueError("Private keys must never be stored in a learned skill.")
        if _URL_RE.search(combined) or _EMAIL_RE.search(combined) or _IPV4_RE.search(combined):
            raise ValueError("Reusable skills cannot store raw URLs, email addresses or IP/network targets.")

    def save(
        self,
        *,
        name: str,
        description: str,
        keywords: list[str],
        instructions: str,
        source: str = "explicit",
        tool_sequence: list[str] | None = None,
    ) -> dict[str, Any]:
        display_name, path = self._path_for(name)
        clean_keywords = list(dict.fromkeys(
            " ".join(str(word).lower().split()).strip()[:80]
            for word in keywords if " ".join(str(word).split()).strip()
        ))
        clean_keywords = clean_keywords[:30]
        clean_description = " ".join(str(description).split()).strip()[:1000]
        clean_instructions = str(instructions).strip()[:6000]
        self._validate_text(display_name, clean_description, clean_keywords, clean_instructions)

        metadata = {
            "name": display_name,
            "description": clean_description,
            "keywords": clean_keywords,
            "source": source[:80],
            "tool_sequence": [str(x)[:80] for x in (tool_sequence or [])[:10]],
            "version": 1,
            "enabled": True,
        }
        document = "---\n" + yaml.safe_dump(
            metadata,
            sort_keys=False,
            allow_unicode=True,
        ) + "---\n" + clean_instructions + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".md.tmp")
        temporary.write_text(document, encoding="utf-8")
        temporary.replace(path)
        return {
            "saved": True,
            "enabled": True,
            "name": display_name,
            "path": str(path),
            "source": source,
            "executable_code_installed": False,
        }

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        skills: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*/SKILL.md"))[: max(1, min(100, limit))]:
            try:
                skill = self._read(path)
            except (OSError, ValueError, yaml.YAMLError):
                continue
            if skill:
                skills.append(skill)
        return skills

    def _read(self, path: Path) -> dict[str, Any] | None:
        document = path.read_text(encoding="utf-8")
        if not document.startswith("---\n"):
            return None
        parts = document.split("---\n", 2)
        if len(parts) != 3:
            return None
        metadata = yaml.safe_load(parts[1])
        if not isinstance(metadata, dict) or not metadata.get("enabled", True):
            return None
        name = str(metadata.get("name") or path.parent.name)
        description = str(metadata.get("description") or "")
        keywords = [str(x).lower() for x in metadata.get("keywords", []) if str(x).strip()]
        instructions = parts[2].strip()
        return {
            "name": name,
            "description": description,
            "keywords": keywords,
            "instructions": instructions,
            "source": str(metadata.get("source") or "unknown"),
            "tool_sequence": [str(x) for x in metadata.get("tool_sequence", [])],
            "path": str(path),
        }

    def matching(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        normalized = " ".join(str(query or "").lower().split())
        matches: list[tuple[int, dict[str, Any]]] = []
        for skill in self.list():
            score = sum(1 for keyword in skill["keywords"] if keyword and keyword in normalized)
            if score:
                matches.append((score, skill))
        matches.sort(key=lambda item: (item[0], item[1]["name"]), reverse=True)
        return [skill for _score, skill in matches[: max(1, min(10, limit))]]

    def auto_learn(self, task: str, successful_tools: list[str]) -> dict[str, Any] | None:
        if len(successful_tools) < 2:
            return None
        names: list[str] = []
        for name in successful_tools:
            normalized = re.sub(r"[^a-z0-9_]+", "", str(name or "").lower())
            if normalized and normalized not in names:
                names.append(normalized)

        # Do not infer or persist a playbook from writes, external sends, security
        # operations or physical actions. These may have high impact and need explicit intent.
        risky_tools = {
            "create_or_update_file", "create_repo", "manage_issues",
            "terminal_execute", "kali_tool_execute", "security_tool_execute",
            "connector_execute", "whatsapp_send_web", "robot_command",
            "robot_mqtt_publish", "robot_ros2_publish", "skill_learn",
        }
        if len(names) < 2 or any(name in risky_tools for name in names):
            return None

        lowered = str(task or "").lower()
        blocked_topics = (
            "password", "passcode", "api key", "secret", "token",
            "private key", "credential", "one-time password", "otp",
            "bank account", "credit card", "medical record",
            "nmap", "penetration test", "exploit", "vulnerability scan",
            "robot", "robotics", "mqtt", "ros2",
        )
        if any(marker in lowered for marker in blocked_topics):
            return None

        clean = str(task or "").strip()
        clean = _URL_RE.sub("<url>", clean)
        clean = _EMAIL_RE.sub("<email>", clean)
        clean = _IPV4_RE.sub("<target>", clean)
        clean = re.sub(r"(?<!\w)/(?:[^ \t\r\n]+)", "<path>", clean)
        clean = " ".join(clean.split())[:180]
        words = []
        for word in _WORD_RE.findall(clean.lower()):
            if word in _STOPWORDS or word.startswith("<"):
                continue
            if word not in words:
                words.append(word)
        if len(words) < 2:
            return None

        slug = _SLUG_RE.sub("-", clean.lower()).strip("-")[:32] or "workflow"
        digest = hashlib.sha256(clean.lower().encode("utf-8")).hexdigest()[:8]
        skill_name = f"learned-{slug}-{digest}"
        instructions = (
            "This playbook was created from a previously completed multi-tool task. "
            "Use it only when the keywords match the current user request. Check current state and inputs first; "
            "never reuse values, paths, URLs, messages or outputs from a prior run. Suggested registered-tool sequence: "
            + " -> ".join(names[:8])
            + ". Inspect every observation and verify the final postcondition. "
            "Saved skill text is advisory only: current user intent, tool permissions and system policies always take precedence."
        )
        return self.save(
            name=skill_name,
            description="Reusable tool workflow for: " + clean,
            keywords=words[:12],
            instructions=instructions,
            source="auto_verified_workflow",
            tool_sequence=names[:8],
        )
