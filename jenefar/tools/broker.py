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
from jenefar.research.sources import fetch_github_repository, fetch_url
from jenefar.coding.repository import RepositoryAnalyzer
from jenefar.tools.security import ScopedSecurityToolExecutor
from jenefar.automation.desktop import DesktopAutomation
from jenefar.robotics.serial_controller import SerialRobotController


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
        self.desktop = DesktopAutomation()
        self.robotics = SerialRobotController()
        self.require_confirmation = require_confirmation
        self.audit = audit or AuditLogger()
        self.scope = scope or ScopePolicy()
        self.security = ScopedSecurityToolExecutor(self.scope)
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
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 120},
                },
                "required": ["command", "timeout"],
                "additionalProperties": False,
            },
            handler=self._terminal_execute,
            requires_confirmation=True,
        ))
        self.registry.register(ToolSpec(
            name="security_tool_execute",
            description="Run a constrained non-shell security profile against a target inside authorized_targets. Profiles are nmap service scan, WhatWeb fingerprinting, and Nikto web-server scanning.",
            parameters={
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "enum": ["nmap", "whatweb", "nikto"]},
                    "target": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 120},
                },
                "required": ["tool", "target", "timeout"],
                "additionalProperties": False,
            },
            handler=self._security_tool_execute,
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_screen_size",
            description="Return the current desktop screen size. Read-only.",
            handler=lambda _args: self.desktop.screen_size(),
        ))
        self.registry.register(ToolSpec(
            name="desktop_click",
            description="Click a desktop coordinate. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "minimum": 0, "maximum": 20000},
                    "y": {"type": "integer", "minimum": 0, "maximum": 20000},
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                },
                "required": ["x", "y", "button"],
                "additionalProperties": False,
            },
            handler=self._desktop_click,
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_type",
            description="Type text into the focused desktop application. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": 4000}},
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=lambda args: self.desktop.type_text(str(args["text"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_press",
            description="Press one safe keyboard key. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
                "additionalProperties": False,
            },
            handler=lambda args: self.desktop.press(str(args["key"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_screenshot",
            description="Capture a desktop screenshot into Jenefar's local data/screenshots directory. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
                "additionalProperties": False,
            },
            handler=lambda args: self.desktop.screenshot(str(args["filename"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="robot_list_ports",
            description="List visible serial ports for robotics hardware. Read-only.",
            handler=lambda _args: self.robotics.list_ports(),
        ))
        self.registry.register(ToolSpec(
            name="robot_command",
            description="Send a bounded robotics command over the configured serial port. Allowed commands: status, stop, forward, backward, left, right, home, servo. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": ["status", "stop", "forward", "backward", "left", "right", "home", "servo"]},
                    "argument": {"type": "string"},
                },
                "required": ["command", "argument"],
                "additionalProperties": False,
            },
            handler=lambda args: self.robotics.command(str(args["command"]), str(args["argument"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="research_fetch_url",
            description="Fetch a public HTTP(S) URL as read-only research text.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_bytes": {"type": "integer", "minimum": 1, "maximum": 2000000},
                },
                "required": ["url", "max_bytes"],
                "additionalProperties": False,
            },
            handler=self._research_fetch_url,
        ))
        self.registry.register(ToolSpec(
            name="research_fetch_github",
            description="Read a public GitHub repository's text/code files for research.",
            parameters={
                "type": "object",
                "properties": {
                    "repository": {"type": "string"},
                    "ref": {"type": "string"},
                    "path": {"type": "string"},
                    "max_files": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["repository", "ref", "max_files"],
                "additionalProperties": False,
            },
            handler=self._research_fetch_github,
        ))
        self.registry.register(ToolSpec(
            name="analyze_github_repository",
            description="Summarize a public GitHub repository without executing downloaded code.",
            parameters={
                "type": "object",
                "properties": {
                    "repository": {"type": "string"},
                    "ref": {"type": "string"},
                },
                "required": ["repository", "ref"],
                "additionalProperties": False,
            },
            handler=self._analyze_github_repository,
        ))
        self.registry.register(ToolSpec(
            name="plan_github_change",
            description="Create a read-only implementation plan for a requested public GitHub repository change.",
            parameters={
                "type": "object",
                "properties": {
                    "repository": {"type": "string"},
                    "ref": {"type": "string"},
                    "task": {"type": "string"},
                },
                "required": ["repository", "ref", "task"],
                "additionalProperties": False,
            },
            handler=self._plan_github_change,
        ))
        self.registry.register(ToolSpec(
            name="extract_local_document",
            description="Read a local PDF, DOCX, Markdown or text document. Privacy-sensitive and requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=self._extract_local_document,
            requires_confirmation=True,
        ))
        self.registry.register(ToolSpec(
            name="scope_check",
            description="Check whether a target is in configured authorized security-testing scope.",
            parameters={
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
                "additionalProperties": False,
            },
            handler=self._scope_check,
        ))

    def _security_tool_execute(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.security.run(
            tool=str(args["tool"]),
            target=str(args["target"]),
            timeout=int(args["timeout"]),
        )
        self.audit.record(
            "security_tool_executed",
            tool=result["tool"],
            target=result["target"],
            profile=result["profile"],
            returncode=result["returncode"],
        )
        return result

    def _desktop_click(self, args: dict[str, Any]) -> dict[str, object]:
        return self.desktop.click(
            int(args["x"]), int(args["y"]), str(args["button"])
        )

    def _analyze_github_repository(self, args: dict[str, Any]) -> dict[str, Any]:
        summary = RepositoryAnalyzer().summarize(str(args["repository"]), ref=str(args["ref"]))
        self.audit.record("github_repository_analyzed", repository=summary.repository, ref=summary.ref)
        return {
            "repository": summary.repository,
            "ref": summary.ref,
            "default_branch": summary.default_branch,
            "file_count": len(summary.files),
            "languages": summary.languages,
            "has_tests": summary.has_tests,
            "has_readme": summary.has_readme,
            "entrypoints": summary.entrypoints,
            "files": [
                {
                    "path": item.path,
                    "size": item.size,
                    "language": item.language,
                    "category": item.category,
                }
                for item in summary.files[:100]
            ],
        }

    def _plan_github_change(self, args: dict[str, Any]) -> dict[str, Any]:
        plan = RepositoryAnalyzer().plan_change(
            str(args["repository"]),
            str(args["task"]),
            ref=str(args["ref"]),
        )
        self.audit.record("github_change_plan", repository=plan.repository, task=plan.task)
        return {
            "repository": plan.repository,
            "task": plan.task,
            "likely_files": plan.likely_files,
            "checks": plan.checks,
            "risks": plan.risks,
            "write_access": False,
        }

    def _extract_local_document(self, args: dict[str, Any]) -> dict[str, Any]:
        from jenefar.docs.ingest import read_document
        path = str(args["path"])
        content = read_document(path)
        self.audit.record("local_document_extracted", path=path)
        return {"path": path, "content": content[:120000]}

    def _research_fetch_url(self, args: dict[str, Any]) -> dict[str, Any]:
        document = fetch_url(str(args["url"]), max_bytes=int(args["max_bytes"]))
        self.audit.record("research_fetch_url", source=document.source)
        return {
            "source": document.source,
            "title": document.title,
            "content": document.content[:100000],
            "metadata": document.metadata,
        }

    def _research_fetch_github(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        path = str(args.get("path") or "").strip()
        documents = fetch_github_repository(
            str(args["repository"]),
            ref=str(args["ref"]),
            paths=[path] if path else None,
            max_files=min(int(args["max_files"]), 10),
        )
        self.audit.record(
            "research_fetch_github",
            repository=str(args["repository"]),
            ref=str(args["ref"]),
            path=path,
            files=len(documents),
        )
        return [
            {
                "source": document.source,
                "title": document.title,
                "content": document.content[:50000],
                "metadata": document.metadata,
            }
            for document in documents
        ]

    def _scope_check(self, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args["target"])
        allowed = self.scope.allows(target)
        self.audit.record("scope_check", target=target, allowed=allowed)
        return {"allowed": allowed, "message": self.scope.explain(target)}

    def _terminal_execute(self, args: dict[str, Any]) -> str:
        return self.terminal.run(
            str(args["command"]), approved=True, timeout=int(args["timeout"])
        )

    def schemas(self, *, allow_action_tools: bool = False) -> list[dict[str, Any]]:
        return self.registry.openai_tools(
            include_confirmation_tools=True,
            include_action_tools=allow_action_tools,
        )

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
