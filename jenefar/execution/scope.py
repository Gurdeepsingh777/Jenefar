from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


class ScopePolicy:
    """Allow-list policy for authorized security-testing targets."""

    def __init__(self, allowed_targets: list[str] | None = None):
        normalized: list[str] = []
        seen: set[str] = set()
        for item in allowed_targets or []:
            value = str(item or "").strip().strip('"').strip("'").lower().rstrip("/")
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)
        self.allowed_targets = normalized

    @staticmethod
    def _host(target: str) -> str:
        value = str(target or "").strip()
        if not value:
            return ""
        # Bare CIDRs aren't URLs: preserve the entire range so it can be
        # compared as a network rather than silently reducing it to a host.
        try:
            return str(ipaddress.ip_network(value, strict=False))
        except ValueError:
            pass
        parsed = urlparse(value if "://" in value else f"//{value}")
        host = parsed.hostname
        return (host or value).strip("[]").lower()

    @staticmethod
    def _network(value: str):
        try:
            return ipaddress.ip_network(value, strict=False)
        except ValueError:
            return None

    def allows(self, target: str) -> bool:
        if not self.allowed_targets:
            return False

        requested = self._host(target)
        if not requested:
            return False

        requested_network = self._network(requested)
        requested_ip = None
        if requested_network is None:
            try:
                requested_ip = ipaddress.ip_address(requested)
            except ValueError:
                requested_ip = None

        for allowed in self.allowed_targets:
            allowed_network = self._network(allowed)
            if allowed_network is not None:
                # A host must be inside the network; a requested CIDR is only
                # allowed when the full requested range is inside the allow-list.
                if requested_network is not None:
                    if requested_network.version == allowed_network.version and requested_network.subnet_of(allowed_network):
                        return True
                elif requested_ip is not None:
                    if requested_ip.version == allowed_network.version and requested_ip in allowed_network:
                        return True
                continue

            # Non-IP hosts are authorized by exact hostname only.
            if requested_network is None and requested_ip is None:
                allowed_host = self._host(allowed)
                if requested.casefold() == allowed_host.casefold():
                    return True

        return False

    def explain(self, target: str) -> str:
        if self.allows(target):
            return f"Target '{target}' is within configured authorization scope."
        if not self.allowed_targets:
            return (
                f"Target '{target}' is outside the configured authorization scope because "
                "the active allow-list is empty. Add the exact host/IP or CIDR to "
                "JENEFAR_AUTHORIZED_TARGETS or config.yaml, then restart Jenefar."
            )
        return (
            f"Target '{target}' is outside the configured authorization scope. "
            "Check the active allow-list at /security/scope and add only targets "
            "you are authorized to test."
        )
