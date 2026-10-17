from __future__ import annotations

import json
import os
import re
import shlex
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
from jenefar.automation.window_control import DesktopWindowControl
from jenefar.robotics.serial_controller import SerialRobotController
from jenefar.robotics.mqtt import MqttRobotController
from jenefar.robotics.ros2 import Ros2RobotController
from jenefar.workspace.service import WorkspaceService
from jenefar.capabilities.store import CapabilityStore
from jenefar.offline.connectivity import internet_available
from jenefar.offline.capabilities import unavailable_online_items, local_items
from jenefar.automation.browser import play_youtube, first_mp3_in_folder
from jenefar.media.song import record_and_recognize
from jenefar.tools.kali import KaliToolManager
from jenefar.vision.screen import ScreenVision
from jenefar.vision.mirror import DesktopMirror
from jenefar.automation.headless import HeadlessDesktopAutomation
from jenefar.skills.manager import SkillManager
from jenefar.connectors.manager import ConnectorManager
from jenefar.memory.advanced import AdvancedMemory
from jenefar.events.engine import EventEngine
from jenefar.rea.client import ReaMCPClient


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
        skills: SkillManager | None = None,
        memory: AdvancedMemory | None = None,
        events: EventEngine | None = None,
        event_handler=None,
        activity_handler=None,
    ):
        self.registry = ToolRegistry()
        self.terminal = TerminalTool()
        desktop_backend = os.getenv("JENEFAR_DESKTOP_BACKEND", "native").strip().lower()
        if desktop_backend in {"headless", "virtual", "safe"}:
            self.desktop = HeadlessDesktopAutomation()
        else:
            self.desktop = DesktopAutomation()
        self.screen_vision = None
        self._screen_vision_ready = False
        self.window_control = DesktopWindowControl()
        self.desktop_mirror = None
        self.robotics = SerialRobotController()
        self.mqtt_robot = MqttRobotController()
        self.ros2_robot = Ros2RobotController()
        self.workspace = WorkspaceService()
        self.capabilities = CapabilityStore()
        self.skills = skills or SkillManager()
        self.memory = memory or AdvancedMemory()
        self.events = events or EventEngine()
        self.event_handler = event_handler
        self.activity_handler = activity_handler
        self.require_confirmation = require_confirmation
        self.audit = audit or AuditLogger()
        self.scope = scope or ScopePolicy()
        self.kali = KaliToolManager(self.scope)
        self.security = ScopedSecurityToolExecutor(self.scope)
        self.connectors = ConnectorManager(
            workspace=self.workspace,
            desktop=self.desktop,
            screen_vision=self._get_screen_vision(),
            robotics=self.robotics,
            mqtt_robot=self.mqtt_robot,
            ros2_robot=self.ros2_robot,
            security=self.security,
        )
        self.rea_connector = ReaMCPClient()
        self.pending: dict[str, PendingToolCall] = {}
        self._task_context: dict[str, str] = {"agent": "", "task": ""}
        self._task_action_log: list[dict[str, str]] = []
        self._register_builtin_tools()
        self._register_phase4_compat_tools()
        self._apply_critical_tool_policy()

    def _rea_status(self) -> dict[str, Any]:
        return self.rea_connector.status()

    def _rea_call(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("tool", "")).strip()
        tool_args = args.get("arguments", {})
        if not isinstance(tool_args, dict):
            raise ValueError("REA tool arguments must be a JSON object.")
        return self.rea_connector.call(name, tool_args)


    def _register_builtin_tools(self) -> None:
        self.registry.register(ToolSpec(
            name="rea_status",
            description="Check optional REA MCP bridge status and Node.js prerequisites.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=lambda _args: self._rea_status(),
        ))
        self.registry.register(ToolSpec(
            name="rea_list_tools",
            description="Connect to REA MCP and list the exact advertised reverse-engineering tools and schemas.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=lambda _args: self.rea_connector.list_tools(),
        ))
        self.registry.register(ToolSpec(
            name="rea_call",
            description="Call an exact advertised REA MCP tool with schema-validated arguments for authorized reverse engineering.",
            parameters={
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "minLength": 1, "maxLength": 160},
                    "arguments": {"type": "object"},
                },
                "required": ["tool", "arguments"],
                "additionalProperties": False,
            },
            handler=self._rea_call,
            requires_confirmation=True,
            action=True,
        ))
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

    @staticmethod
    def _terminal_command_is_critical(command: str) -> bool:
        """Permit bounded, low-risk local inspection/test commands without prompts."""
        raw = str(command or "").strip()
        if not raw or any(char in raw for char in ("\n", "\r", chr(96), "$", ">", "<", "&", "(", ")")):
            return True
        segments = re.split(r"\s*(?:&&|\|\||;|\|)\s*", raw)
        if not segments or any(not segment.strip() for segment in segments):
            return True
        forbidden = {
            "sudo", "su", "doas", "rm", "rmdir", "shred", "wipe", "wipefs",
            "dd", "mkfs", "fdisk", "parted", "mount", "umount", "reboot",
            "shutdown", "poweroff", "systemctl", "service", "kill", "pkill",
            "chmod", "chown", "chattr", "setfacl", "iptables", "nft", "ufw",
            "curl", "wget", "nc", "netcat", "nmap", "masscan", "nikto",
            "sqlmap", "hydra", "aircrack-ng", "hashcat", "responder",
        }
        read_only = {
            "pwd", "ls", "tree", "cat", "head", "tail", "less", "more",
            "file", "stat", "du", "df", "grep", "rg", "wc", "cut",
            "sort", "uniq", "tr", "printf", "echo", "date", "whoami", "id",
            "uname", "hostname", "which", "whereis", "free", "ps", "uptime",
        }
        for segment in segments:
            try:
                tokens = shlex.split(segment)
            except ValueError:
                return True
            if not tokens:
                return True
            executable = tokens[0].rsplit("/", 1)[-1].lower()
            args = tokens[1:]
            if executable in forbidden:
                return True
            if executable == "find":
                if any(arg in {"-exec", "-execdir", "-delete", "-ok"} for arg in args):
                    return True
                continue
            if executable == "cd":
                if len(args) > 1:
                    return True
                continue
            if executable in read_only:
                continue
            if executable == "ip":
                normalized = [arg.lower() for arg in args if not arg.startswith("-")]
                if normalized and normalized[0] in {"addr", "address", "route", "link", "neigh"}:
                    if any(arg in {"flush", "del", "delete", "add", "replace", "set"} for arg in normalized):
                        return True
                    continue
                return True
            if executable == "git":
                if not args:
                    return True
                subcommand = args[0].lower()
                safe_git = {
                    "status", "diff", "log", "show", "branch", "rev-parse",
                    "ls-files", "grep", "blame", "describe", "tag", "remote",
                    "shortlog", "version", "fetch",
                }
                if subcommand not in safe_git:
                    return True
                if subcommand == "branch" and any(arg in {"-d", "-D", "--delete"} for arg in args):
                    return True
                if subcommand == "tag" and any(arg in {"-d", "--delete"} for arg in args):
                    return True
                if subcommand == "remote" and any(arg in {"add", "remove", "set-url"} for arg in args):
                    return True
                continue
            if executable in {"python", "python3"}:
                if not args or args[0] in {"--version", "-V"}:
                    continue
                if len(args) >= 2 and args[0] == "-m" and args[1] in {"pytest", "unittest", "compileall"}:
                    continue
                if args[0] in {"run.py", "./run.py"} and len(args) >= 2 and args[1] in {"--doctor", "--gui-smoke-test"}:
                    continue
                return True
            if executable in {"pytest", "py.test"}:
                continue
            if executable == "node" and args[:1] == ["--check"]:
                continue
            if executable == "npm" and args[:1] == ["test"]:
                continue
            return True
        return False

    def _apply_critical_tool_policy(self) -> None:
        critical_names = {
            "terminal_execute",
            "whatsapp_send_web",
            "connector_execute",
            "kali_tool_execute",
            "security_tool_execute",
            "robot_mqtt_publish",
            "robot_ros2_publish",
            "robot_command",
        }
        for name in critical_names:
            try:
                self.registry.get(name).critical = True
            except KeyError:
                continue

    def set_task_context(self, *, agent: str = "", task: str = "") -> None:
        self._task_context = {
            "agent": str(agent or ""),
            "task": str(task or ""),
        }
        self._task_action_log = []

    def consume_task_actions(self) -> list[dict[str, str]]:
        """Return successful tool names only; arguments/results are never retained."""
        actions = list(self._task_action_log)
        self._task_action_log = []
        return actions

    def clear_task_context(self) -> None:
        self._task_context = {"agent": "", "task": ""}
        self._task_action_log = []

    @staticmethod
    def _explicit_screenshot_request(task: str) -> bool:
        lowered = str(task or "").lower()
        return any(marker in lowered for marker in (
            "screenshot le lo", "screenshot le", "screenshot bana",
            "screenshot save", "take a screenshot", "capture a screenshot",
            "save a screenshot", "screenshot chahiye",
        ))

    def _guard_screen_tool(self, name: str) -> str | None:
        agent = self._task_context.get("agent", "")
        task = self._task_context.get("task", "")
        if agent != "gui_vision":
            return None
        if name == "terminal_execute":
            return json.dumps({
                "status": "error",
                "error": "Screen-reading tasks must not use terminal_execute. Use desktop_observe or semantic GUI tools.",
            })
        if name == "desktop_screenshot" and not self._explicit_screenshot_request(task):
            return json.dumps({
                "status": "error",
                "error": "desktop_screenshot is only available when the user explicitly asks for a screenshot.",
            })
        return None

    def _activity(self, state: str, text: str) -> None:
        if self.activity_handler is not None:
            try:
                self.activity_handler(state, text)
            except Exception:
                pass

    def _get_desktop_mirror(self):
        if self.desktop_mirror is None:
            self.desktop_mirror = DesktopMirror(
                self.desktop,
                self._get_screen_vision(),
                self.window_control,
            )
        return self.desktop_mirror

    def _get_screen_vision(self):
        if self.screen_vision is None:
            self.screen_vision = ScreenVision(self.desktop)
            self._screen_vision_ready = True
        return self.screen_vision


