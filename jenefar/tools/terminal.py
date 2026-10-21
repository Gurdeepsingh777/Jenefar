from __future__ import annotations

import subprocess
import time

from jenefar.tools.safety import ToolPolicy, ToolRequest


MAX_TERMINAL_OUTPUT_CHARS = 16000
MAX_TERMINAL_TIMEOUT_SECONDS = 120


class TerminalTool:
    """Approval-gated terminal adapter with bounded execution and explicit exit status."""

    def __init__(self, policy: ToolPolicy | None = None):
        self.policy = policy or ToolPolicy()

    def run(self, command: str, *, approved: bool = False, timeout: int = 30) -> str:
        request = ToolRequest(name="terminal", arguments={"command": command})
        if not self.policy.authorize(request, confirmed=approved):
            raise PermissionError("Terminal execution requires explicit confirmation.")

        raw = str(command or "").strip()
        if not raw:
            raise ValueError("Terminal command cannot be empty.")
        try:
            bounded_timeout = max(1, min(int(timeout), MAX_TERMINAL_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            bounded_timeout = 30

        started = time.monotonic()
        try:
            completed = subprocess.run(
                raw,
                shell=True,
                capture_output=True,
                text=True,
                timeout=bounded_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - started
            raise TimeoutError(
                f"Terminal command timed out after {bounded_timeout}s "
                f"(elapsed {elapsed:.1f}s). The command may have been terminated."
            ) from exc

        elapsed = time.monotonic() - started
        stdout = str(completed.stdout or "")
        stderr = str(completed.stderr or "")
        output = (stdout + stderr).strip()
        truncated = len(output) > MAX_TERMINAL_OUTPUT_CHARS
        if truncated:
            output = output[:MAX_TERMINAL_OUTPUT_CHARS] + "\n[output truncated at 16000 characters]"
        status = (
            f"[exit_code={completed.returncode}; elapsed={elapsed:.2f}s; timeout={bounded_timeout}s]"
        )
        return status + ("\n" + output if output else "\n[no stdout/stderr]")
