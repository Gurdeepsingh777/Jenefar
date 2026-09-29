from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from jenefar.execution.audit import AuditLogger
from jenefar.execution.scope import ScopePolicy
from jenefar.tools.discovery import discover_tools
from jenefar.tools.registry import ToolRegistry, ToolSpec
from jenefar.tools.terminal import TerminalTool

@dataclass
class PendingToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

class ToolBroker:
    """Single gateway between model function-calls and local tools."""

    def __init__(
        self,
        *,
        require_confirmation: bool = True,
        audit: AuditLogger | None = None,
        scope: ScopePolicy | None = None,
    ):
        self.registry = ToolRegistry()
        self.terminal = TerminalTool()
        self.require_confirmation = require_confirmation
        self.audit = audit or AuditLogger()
        self.scope = scope or ScopePolicy()
        self.pending: dict[str, PendingToolCall] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        self.registry.register(ToolSpec(
            name="discover_kali_tools",
            description="List common Kali/Linux security tools and whether each executable is installed. This never executes a security tool.",
            handler=lambda _args: [
                {
                    "name": t.name,
                    "category": t.category,
                    "command": t.command,
                    "installed": t.installed,
                    "description": t.description,
                }
                for t in discover_tools()
            ],
        ))
        self.registry.register(ToolSpec(
            name="terminal_execute",
            description="Execute one exact shell command on the local machine. This is high-impact and always requires explicit user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Exact shell command to execute."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds.", "minimum": 1, "maximum": 120},
                },
                "required": ["command", "timeout"],
                "additionalProperties": False,
            },
            handler=self._terminal_execute,
            requires_confirmation=True,
        ))
        self.registry.register(ToolSpec(
            name="scope_check",
            description="Check whether a hostname, IP address, URL host, or CIDR target is in Jenefar's configured authorized testing scope.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                },
                "required": ["target"],
                "additionalProperties": False,
            },
            handler=self._scope_check,
        ))

    def _scope_check(self, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args["target"])
        allowed = self.scope.allows(target)
        self.audit.record("scope_check", target=target, allowed=allowed)
        return {"allowed": allowed, "message": self.scope.explain(target)}

    def _terminal_execute(self, args: dict[str, Any]) -> str:
        return self.terminal.run(
            str(args["command"]),
            approved=True,
            timeout=int(args["timeout"]),
        )

    def schemas(self, *, allow_action_tools: bool = False) -> list[dict[str, Any]]:
        # Confirmation is enforced by invoke(); hiding the schema would prevent the
        # model from ever requesting an approval-gated action.
        return self.registry.openai_tools(include_confirmation_tools=True)

    def invoke(self, name: str, arguments: dict[str, Any], *, confirmed: bool = False) -> str:
        try:
            spec = self.registry.get(name)
        except KeyError:
            self.audit.record("tool_unknown", tool=name)
            return json.dumps({"status": "error", "error": f"Unknown tool: {name}"})

        if spec.requires_confirmation and self.require_confirmation and not confirmed:
            pending_id = uuid.uuid4().hex
            self.pending[pending_id] = PendingToolCall(pending_id, name, arguments)
            self.audit.record(
                "tool_approval_requested",
                pending_id=pending_id,
                tool=name,
                arguments=arguments,
            )
            return json.dumps({
                "status": "approval_required",
                "pending_id": pending_id,
                "tool": name,
                "message": "Explicit user confirmation is required before this tool can execute.",
            })

        try:
            value = spec.handler(arguments)
            self.audit.record("tool_executed", tool=name, arguments=arguments, result=value)
            return json.dumps({"status": "ok", "result": value}, ensure_ascii=False, default=str)
        except Exception as exc:
            self.audit.record(
                "tool_error",
                tool=name,
                arguments=arguments,
                error=f"{type(exc).__name__}: {exc}",
            )
            return json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"})

    def approve(self, pending_id: str) -> str:
        pending = self.pending.pop(pending_id, None)
        if pending is None:
            return json.dumps({"status": "error", "error": "Unknown or expired pending tool call."})
        self.audit.record("tool_approved", pending_id=pending_id, tool=pending.name)
        return self.invoke(pending.name, pending.arguments, confirmed=True)
