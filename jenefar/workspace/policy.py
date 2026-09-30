from __future__ import annotations

import os
from pathlib import Path


class WorkspacePolicy:
    def __init__(self, roots: list[str] | None = None) -> None:
        configured = roots or [
            str(Path.cwd()),
            "/home/jenefar/Document/Tools",
        ]
        env_roots = [
            item.strip()
            for item in os.getenv("JENEFAR_WORKSPACE_ROOTS", "").split(os.pathsep)
            if item.strip()
        ]
        self.roots = [Path(item).expanduser().resolve() for item in [*configured, *env_roots]]

    def _normalize_requested_path(self, path: str | Path) -> Path:
        raw = str(path).strip()
        if raw in {"", "/"}:
            return self.roots[0]
        return Path(path).expanduser().resolve()

    def allowed(self, path: str | Path) -> bool:
        candidate = self._normalize_requested_path(path)
        return any(candidate == root or root in candidate.parents for root in self.roots)

    def require_allowed(self, path: str | Path) -> Path:
        candidate = self._normalize_requested_path(path)
        if not self.allowed(candidate):
            roots = ", ".join(str(root) for root in self.roots)
            raise PermissionError(
                f"Path is outside Jenefar workspace scope: {candidate}. Allowed roots: {roots}"
            )
        return candidate
