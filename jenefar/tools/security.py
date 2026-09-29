from __future__ import annotations

import shlex
import shutil
import subprocess
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

    def run(self, *, tool: str, target: str, timeout: int = 60) -> dict[str, object]:
        tool = tool.strip().lower()
        target = target.strip()

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

        profile, profile_args = self.PROFILES[tool]
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

        return {
            "tool": tool,
            "profile": profile,
            "target": target,
            "command": " ".join(shlex.quote(part) for part in command),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-20000:],
            "stderr": completed.stderr[-10000:],
        }
