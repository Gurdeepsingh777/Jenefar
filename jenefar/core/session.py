from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Session:
    id: str
    messages: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def recent(self, limit: int = 20) -> list[dict[str, str]]:
        return self.messages[-limit:]
