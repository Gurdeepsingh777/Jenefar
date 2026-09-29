from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv
import yaml

ROOT = Path(__file__).resolve().parents[2]

@dataclass
class Config:
    name: str = "Jenefar"
    wake_phrases: list[str] = field(default_factory=lambda: ["hi jenefar", "hello jenefar"])
    require_wake_phrase: bool = True
    single_turn_sleep: bool = True
    require_confirmation_for_tools: bool = True
    command_timeout_seconds: int = 30
    authorized_targets: list[str] = field(default_factory=list)
    audit_log_path: str = "data/audit.jsonl"

def load_config() -> Config:
    load_dotenv(ROOT / ".env")
    raw: dict = {}
    config_path = ROOT / "config.yaml"
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    assistant = raw.get("assistant", {})
    runtime = raw.get("runtime", {})
    security = raw.get("security", {})

    env_phrases = [
        item.strip().lower()
        for item in os.getenv("JENEFAR_WAKE_PHRASES", "Hi Jenefar,Hello Jenefar").split(",")
        if item.strip()
    ]
    env_targets = [
        item.strip().lower()
        for item in os.getenv("JENEFAR_AUTHORIZED_TARGETS", "").split(",")
        if item.strip()
    ]

    phrases = assistant.get("wake_phrases") or env_phrases
    targets = security.get("authorized_targets") or env_targets

    return Config(
        name=str(assistant.get("name") or os.getenv("JENEFAR_NAME", "Jenefar")),
        wake_phrases=[str(p).strip().lower() for p in phrases],
        require_wake_phrase=bool(assistant.get("require_wake_phrase", True)),
        single_turn_sleep=bool(assistant.get("single_turn_sleep", True)),
        require_confirmation_for_tools=bool(runtime.get("require_confirmation_for_tools", True)),
        command_timeout_seconds=int(runtime.get("command_timeout_seconds", 30)),
        authorized_targets=[str(x).strip().lower() for x in targets if str(x).strip()],
        audit_log_path=str(security.get("audit_log_path", "data/audit.jsonl")),
    )
