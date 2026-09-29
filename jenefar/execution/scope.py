from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

class ScopePolicy:
    """Allow-list policy for authorized security-testing targets."""

    def __init__(self, allowed_targets: list[str] | None = None):
        self.allowed_targets = [x.strip().lower() for x in (allowed_targets or []) if x.strip()]

    def _normalize(self, target: str) -> str:
        value = target.strip().lower()
        parsed = urlparse(value if "://" in value else f"//{value}")
        host = parsed.hostname
        return host or value

    def allows(self, target: str) -> bool:
        if not self.allowed_targets:
            return False

        host = self._normalize(target)
        for allowed in self.allowed_targets:
            if "/" in allowed:
                try:
                    if ipaddress.ip_address(host) in ipaddress.ip_network(allowed, strict=False):
                        return True
                except ValueError:
                    continue
            elif host == self._normalize(allowed):
                return True
        return False

    def explain(self, target: str) -> str:
        if self.allows(target):
            return f"Target '{target}' is within configured authorization scope."
        return (
            f"Target '{target}' is outside the configured authorization scope. "
            "Add the exact hostname/IP or CIDR to authorized_targets before testing."
        )
