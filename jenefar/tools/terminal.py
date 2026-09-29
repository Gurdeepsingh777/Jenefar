import subprocess
from jenefar.tools.safety import ToolRequest, ToolPolicy

class TerminalTool:
    def __init__(self, policy: ToolPolicy | None = None):
        self.policy = policy or ToolPolicy()

    def run(self, command: str, *, approved: bool = False, timeout: int = 30) -> str:
        request = ToolRequest(name="terminal", arguments={"command": command})
        if not self.policy.authorize(request, confirmed=approved):
            raise PermissionError("Terminal execution requires explicit confirmation.")
        completed = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return (completed.stdout + completed.stderr).strip()
