from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid4().hex)
    messages: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def session_id(self) -> str:
        return self.id

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def recent(self, limit: int = 20) -> list[dict[str, str]]:
        return self.messages[-limit:]
