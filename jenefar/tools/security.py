from __future__ import annotations

import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET
import ipaddress
from urllib.parse import urlparse

from jenefar.execution.scope import ScopePolicy


class ScopedSecurityToolExecutor:
    """Constrained, non-shell profiles for targets inside authorized scope."""

    PROFILES = {
        "nmap": (
            "service_scan",
            ("-sV", "--top-ports", "100", "--max-retries", "2", "-T3"),
        ),
        "whatweb": (
            "web_fingerprint",
            ("--no-errors",),
        ),
        "nikto": (
            "web_server_scan",
            ("-nointeractive",),
        ),
    }

    def __init__(self, scope: ScopePolicy):
        self.scope = scope

    @staticmethod
    def _host(target: str) -> str:
        value = target.strip()
        parsed = urlparse(value if "://" in value else f"//{value}")
        return parsed.hostname or value

    def run(
        self,
        *,
        tool: str,
        target: str,
        timeout: int = 60,
        mode: str = "services",
    ) -> dict[str, object]:
        tool = tool.strip().lower()
        target = target.strip()
        mode = mode.strip().lower()

        if tool not in self.PROFILES:
            raise ValueError(f"Security tool '{tool}' is not in the execution allow-list.")
        if not target:
            raise ValueError("A target is required.")
        if not self.scope.allows(target):
            raise PermissionError(self.scope.explain(target))
        if timeout < 1 or timeout > 120:
            raise ValueError("Timeout must be between 1 and 120 seconds.")

        executable = shutil.which(tool)
        if not executable:
            raise FileNotFoundError(f"{tool} is not installed or not available on PATH.")

        if tool == "nmap" and mode not in {"live_hosts", "services"}:
            raise ValueError("Nmap mode must be 'live_hosts' or 'services'.")
        if tool != "nmap" and mode != "services":
            raise ValueError("Host-discovery mode is supported only by nmap.")

        profile, profile_args = self.PROFILES[tool]
        if tool == "nmap" and mode == "live_hosts":
            profile = "host_discovery"
            # Avoid ARP/raw-socket discovery so this works for ordinary users.
            # Nmap uses TCP connect probes in unprivileged mode.
            profile_args = (
                "--unprivileged",
                "-sn",
                "-PS22,80,443,445,3389,8080",
                "-oX",
                "-",
            )

        # Keep CIDR notation intact for nmap. Parsing it as a URL hostname
        # silently drops the prefix and scans only the network address.
        try:
            ipaddress.ip_network(target, strict=False)
            command_target = target
        except ValueError:
            command_target = self._host(target)
        if tool in {"whatweb", "nikto"} and "://" not in command_target:
            command_target = f"http://{command_target}"

        if tool == "nikto":
            command = [executable, *profile_args, "-host", command_target]
        else:
            command = [executable, *profile_args, command_target]

        completed = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        result: dict[str, object] = {
            "tool": tool,
            "profile": profile,
            "target": target,
            "command": " ".join(shlex.quote(part) for part in command),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-20000:],
            "stderr": completed.stderr[-10000:],
        }
        if profile == "host_discovery":
            if completed.returncode != 0:
                result["scan_error"] = completed.stderr[-3000:] or "Nmap host discovery failed."
            try:
                document = ET.fromstring(completed.stdout)
                hosts = []
                for host in document.findall("host"):
                    status = host.find("status")
                    if status is None or status.get("state") != "up":
                        continue
                    addresses = [
                        node.get("addr", "")
                        for node in host.findall("address")
                        if node.get("addr")
                    ]
                    names = [
                        node.get("name", "")
                        for node in host.findall("./hostnames/hostname")
                        if node.get("name")
                    ]
                    hosts.append({"addresses": addresses, "hostnames": names})
                result["hosts"] = hosts
                result["live_host_count"] = len(hosts)
            except ET.ParseError:
                result["hosts"] = []
                result["live_host_count"] = 0
                result["parse_error"] = "Nmap did not return valid XML host-discovery output."
        return result
