from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class UISettings:
    """Non-secret persistent desktop UI preferences."""

    def __init__(self, path: str | Path = "data/ui_settings.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        current = self.load()
        allowed = {"theme", "avatar_mode", "avatar_port", "realtime_enabled"}
        for key, value in values.items():
            if key in allowed:
                current[key] = value
        self.path.write_text(
            json.dumps(current, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return current
