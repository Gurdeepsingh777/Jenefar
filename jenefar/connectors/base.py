from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ConnectorAction:
    name: str
    description: str
    requires_confirmation: bool = False


@dataclass(frozen=True)
class ConnectorManifest:
    name: str
    version: str
    description: str
    online_required: bool
    actions: tuple[ConnectorAction, ...] = ()
    source: str = "builtin"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "online_required": self.online_required,
            "actions": [
                {
                    "name": action.name,
                    "description": action.description,
                    "requires_confirmation": action.requires_confirmation,
                }
                for action in self.actions
            ],
            "source": self.source,
        }


class Connector:
    def __init__(
        self,
        manifest: ConnectorManifest,
        handlers: dict[str, Callable[[dict[str, Any]], Any]],
    ) -> None:
        self.manifest = manifest
        self.handlers = handlers

    def execute(self, action: str, arguments: dict[str, Any]) -> Any:
        try:
            handler = self.handlers[action]
        except KeyError as exc:
            raise KeyError(
                f"Unsupported action '{action}' for connector '{self.manifest.name}'."
            ) from exc
        return handler(arguments)

    def action(self, action: str) -> ConnectorAction:
        for item in self.manifest.actions:
            if item.name == action:
                return item
        raise KeyError(
            f"Unsupported action '{action}' for connector '{self.manifest.name}'."
        )


__all__ = ["Connector", "ConnectorAction", "ConnectorManifest"]
