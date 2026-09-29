from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class CapabilityStore:
    def __init__(self, path: str | Path = "data/capabilities.json") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"capabilities": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"capabilities": []}
        except Exception:
            return {"capabilities": []}

    def list(self) -> list[dict[str, Any]]:
        return list(self._load().get("capabilities", []))

    def add(self, capability: str, notes: str = "") -> dict[str, Any]:
        capability = " ".join(str(capability).split()).strip()
        if not capability:
            raise ValueError("Capability text cannot be empty.")

        with self._lock:
            data = self._load()
            items = data.setdefault("capabilities", [])
            item = {
                "capability": capability,
                "notes": " ".join(str(notes).split()).strip(),
                "added_by": "user_request",
            }
            if not any(x.get("capability", "").lower() == capability.lower() for x in items):
                items.append(item)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return item
