from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolRequest:
    name: str
    arguments: dict
    requires_confirmation: bool = True
    reason: str = ""


class ToolPolicy:
    """Central policy gate for future tool execution."""

    def __init__(self, require_confirmation: bool = True) -> None:
        self.require_confirmation = require_confirmation

    def authorize(self, request: ToolRequest, *, confirmed: bool = False) -> bool:
        if not self.require_confirmation or not request.requires_confirmation:
            return True
        return confirmed
