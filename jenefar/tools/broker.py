from __future__ import annotations

import json
import os
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
from jenefar.automation.headless import HeadlessDesktopAutomation
from jenefar.skills.manager import SkillManager
from jenefar.connectors.manager import ConnectorManager
from jenefar.memory.advanced import AdvancedMemory
from jenefar.events.engine import EventEngine


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
        self.pending: dict[str, PendingToolCall] = {}
        self._register_builtin_tools()
        self._register_phase4_compat_tools()

    def _activity(self, state: str, text: str) -> None:
        if self.activity_handler is not None:
            try:
                self.activity_handler(state, text)
            except Exception:
                pass

    def _get_screen_vision(self):
        if self.screen_vision is None:
            self.screen_vision = ScreenVision(self.desktop)
            self._screen_vision_ready = True
        return self.screen_vision

    @staticmethod
    def _local_time() -> dict[str, str]:
        from datetime import datetime

        now = datetime.now().astimezone()
        return {
            "iso": now.isoformat(),
            "date": now.strftime("%A, %d %B %Y"),
            "time": now.strftime("%I:%M:%S %p"),
            "timezone": now.tzname() or "local",
        }

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
            name="dismiss_offline_notice",
            description="Acknowledge and close Jenefar's current offline-capability notice.",
            handler=lambda _args: {"closed": True, "message": "Offline capability notice closed."},
        ))
        self.registry.register(ToolSpec(
            name="whatsapp_open_web",
            description="Open the logged-in WhatsApp Web session in the visible browser. Uses Jenefar's WhatsApp helper when available, otherwise opens web.whatsapp.com.",
            handler=lambda _args: self._whatsapp_open_web(),
        ))
        self.registry.register(ToolSpec(
            name="whatsapp_send_web",
            description="Send a WhatsApp message through the user's visible/logged-in WhatsApp Web session. Prefer a contact name when known; the helper uses the existing browser session. Explicit confirmation is required.",
            parameters={
                "type": "object",
                "properties": {
                    "contact": {"type": "string", "maxLength": 200},
                    "message": {"type": "string", "maxLength": 4000},
                    "phone": {"type": ["string", "null"], "maxLength": 32},
                },
                "required": ["contact", "message", "phone"],
                "additionalProperties": False,
            },
            handler=self._whatsapp_send_web,
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_backend_status",
            description="Check whether local desktop automation is ready before screen, mouse, keyboard or GUI actions.",
            parameters={"type":"object","properties":{},"required":[],"additionalProperties":False},
            handler=lambda _args: self.desktop.backend_status(),
        ))
        self.registry.register(ToolSpec(
            name="local_time",
            description="Return the current local computer date, time, timezone, and ISO timestamp. Safe read-only system information; no confirmation is required.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda _args: self._local_time(),
        ))

        self.registry.register(ToolSpec(
            name="offline_status",
            description="Report online/offline connectivity and which capabilities are unavailable when internet is not reachable.",
            handler=lambda _args: {
                "connectivity": "online" if internet_available() else "offline",
                "online_only_unavailable": unavailable_online_items(),
                "local_capabilities": local_items(),
            },
        ))
        self.registry.register(ToolSpec(
            name="skill_catalog",
            description="List available declarative Jenefar skills and whether each skill is enabled.",
            handler=lambda _args: self.skills.list(),
        ))
        self.registry.register(ToolSpec(
            name="skill_enable",
            description="Enable a registered Jenefar skill. This changes persistent skill configuration; it does not grant security authorization.",
            parameters={
                "type": "object",
                "properties": {"skill": {"type": "string"}},
                "required": ["skill"],
                "additionalProperties": False,
            },
            handler=lambda args: self.skills.enable(str(args["skill"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="skill_disable",
            description="Disable a registered Jenefar skill without deleting it. This changes persistent skill configuration.",
            parameters={
                "type": "object",
                "properties": {"skill": {"type": "string"}},
                "required": ["skill"],
                "additionalProperties": False,
            },
            handler=lambda args: self.skills.disable(str(args["skill"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="skill_install_manifest",
            description="Install a declarative skill manifest from a file inside configured JENEFAR_SKILL_ROOTS. No arbitrary code is executed.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=lambda args: self.skills.install_manifest(str(args["path"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="connector_catalog",
            description="List trusted connector adapters and their bounded actions.",
            handler=lambda _args: self.connectors.list(),
        ))
        self.registry.register(ToolSpec(
            name="connector_status",
            description="Return metadata for one trusted connector.",
            parameters={
                "type": "object",
                "properties": {"connector": {"type": "string"}},
                "required": ["connector"],
                "additionalProperties": False,
            },
            handler=lambda args: self.connectors.status(str(args["connector"])),
        ))
        self.registry.register(ToolSpec(
            name="connector_execute",
            description="Execute one bounded action through a trusted connector adapter. Explicit confirmation is required for every connector call.",
            parameters={
                "type": "object",
                "properties": {
                    "connector": {"type": "string"},
                    "action": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["connector", "action", "arguments"],
                "additionalProperties": False,
            },
            handler=lambda args: self._connector_execute(
                str(args["connector"]),
                str(args["action"]),
                dict(args.get("arguments") or {}),
            ),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="scope_add_capability",
            description="Persist a user-requested capability into Jenefar's learned capability scope. This changes descriptive capability memory only; security authorization and execution policies remain enforced.",
            parameters={
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "maxLength": 500},
                    "notes": {"type": "string", "maxLength": 2000},
                },
                "required": ["capability", "notes"],
                "additionalProperties": False,
            },
            handler=lambda args: self.capabilities.add(
                str(args["capability"]),
                str(args["notes"]),
            ),
        ))
        self.registry.register(ToolSpec(
            name="workspace_list_directory",
            description="List files/directories inside Jenefar's authorized local workspace roots. Read-only.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "max_items": {"type": "integer", "minimum": 1, "maximum": 500}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.list_directory(
                str(args["path"]),
                int(args.get("max_items", 200)),
            ),
        ))
        self.registry.register(ToolSpec(
            name="workspace_inspect_file",
            description="Read an authorized local text/code file for analysis. Read-only.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer", "minimum": 1, "maximum": 500000}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.inspect_file(
                str(args["path"]),
                int(args.get("max_bytes", 200000)),
            ),
        ))
        self.registry.register(ToolSpec(
            name="workspace_run_python",
            description="Run an authorized local .py file and return stdout/stderr. Execution requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
                },
                "required": ["path", "timeout"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.run_python(
                str(args["path"]),
                int(args["timeout"]),
            ),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="workspace_validate_python",
            description="Validate syntax of an authorized Python file with py_compile. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 120},
                },
                "required": ["path", "timeout"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.validate_python(
                str(args["path"]),
                int(args["timeout"]),
            ),
            requires_confirmation=False,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="workspace_run_pytest",
            description="Run pytest against an authorized local file or directory. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
                },
                "required": ["path", "timeout"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.run_pytest(
                str(args["path"]),
                int(args["timeout"]),
            ),
            requires_confirmation=False,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="workspace_create_file",
            description="Create a new text/code file inside an authorized local workspace root. Parent directories are created when needed.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "maxLength": 500000},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.create_file(
                str(args["path"]),
                str(args["content"]),
            ),
            requires_confirmation=False,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="workspace_edit_file",
            description="Edit or create an authorized local text/code file by replacing its complete content. Existing files get a timestamped backup and diff. User-directed coding tasks may use this directly.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "new_content": {"type": "string", "maxLength": 500000},
                },
                "required": ["path", "new_content"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.edit_file(
                str(args["path"]),
                str(args["new_content"]),
            ),
            requires_confirmation=False,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="workspace_diff",
            description="Show the latest Jenefar backup diff for an authorized local file. Read-only.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=lambda args: self.workspace.diff_file(str(args["path"])),
        ))
        self.registry.register(ToolSpec(
            name="kali_catalog",
            description="List the curated Kali Linux tool catalog with tactic/category and installed status. Read-only.",
            parameters={
                "type": "object",
                "properties": {
                    "tactic": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda args: self.kali.catalog_list(
                str(args.get("category") or "") or None,
                str(args.get("tactic") or "") or None,
            ),
        ))
        self.registry.register(ToolSpec(
            name="kali_tool_execute",
            description="Execute one installed tool from the curated Kali catalog with explicit confirmation. Network targets must be inside authorized_targets.",
            parameters={
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}, "maxItems": 80},
                    "target": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
                },
                "required": ["tool", "args", "target", "timeout"],
                "additionalProperties": False,
            },
            handler=lambda args: self.kali.execute(
                tool=str(args["tool"]),
                args=[str(value) for value in args["args"]],
                target=str(args["target"]),
                timeout=int(args["timeout"]),
            ),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="browser_play_youtube",
            description="Search YouTube and open the first matching result in the preferred browser. Firefox is preferred, then Chrome/Chromium.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 300}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=lambda args: self._browser_play_youtube(str(args["query"])),
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="play_local_mp3",
            description="Play the first MP3 file found recursively under an authorized local folder using VLC.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=lambda args: first_mp3_in_folder(str(args["path"])),
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="recognize_song_from_microphone",
            description="Record a short microphone sample of a song playing nearby and recognize it using the optional online recognition backend.",
            parameters={
                "type": "object",
                "properties": {"seconds": {"type": "integer", "minimum": 4, "maximum": 20}},
                "required": ["seconds"],
                "additionalProperties": False,
            },
            handler=lambda args: record_and_recognize(int(args["seconds"])),
            requires_confirmation=True,
            action=True,
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
            name="desktop_observe",
            description="Read the current screen with the configured vision model for the user's explicit screen-reading request. Read-only. This does not save a screenshot.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 500},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=lambda args: self.screen_vision.read_screen(str(args["query"])),
            requires_confirmation=False,
            action=False,
        ))
        self.registry.register(ToolSpec(
            name="desktop_find_element",
            description="Use current screen vision to locate a semantic UI element such as an address bar, button, menu or search box. Read-only.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 500}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=lambda args: self.screen_vision.locate(str(args["query"])),
            requires_confirmation=False,
            action=False,
        ))
        self.registry.register(ToolSpec(
            name="desktop_click_element",
            description="Analyze the current screen, click a semantic UI element, capture a fresh screen, and optionally verify a visible postcondition. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 500},
                    "verify": {"type": ["string", "null"], "maxLength": 500},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=lambda args: self.screen_vision.locate_and_click(
                str(args["query"]),
                verify=str(args["verify"]) if args.get("verify") else None,
            ),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_type_into_element",
            description="Analyze the current screen, click a semantic input element, type text, capture a fresh screen, and optionally verify a visible postcondition. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 500},
                    "text": {"type": "string", "maxLength": 4000},
                    "verify": {"type": ["string", "null"], "maxLength": 500},
                },
                "required": ["query", "text"],
                "additionalProperties": False,
            },
            handler=lambda args: self.screen_vision.locate_and_type(
                str(args["query"]),
                str(args["text"]),
                verify=str(args["verify"]) if args.get("verify") else None,
            ),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_hotkey",
            description="Press a bounded safe keyboard shortcut such as ctrl+l or ctrl+c. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                },
                "required": ["keys"],
                "additionalProperties": False,
            },
            handler=lambda args: self.desktop.hotkey([str(item) for item in args["keys"]]),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="desktop_scroll",
            description="Scroll the current desktop by a bounded number of clicks. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {"clicks": {"type": "integer", "minimum": -20, "maximum": 20}},
                "required": ["clicks"],
                "additionalProperties": False,
            },
            handler=lambda args: self.desktop.scroll(int(args["clicks"])),
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
            description="Capture and save a desktop screenshot into Jenefar's local data/screenshots directory. Use ONLY when the user explicitly asks to take, save, or show a screenshot; never use it as a screen-inspection workaround. Requires explicit confirmation.",
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
            name="robot_mqtt_telemetry",
            description="Read the latest telemetry message from the configured MQTT robotics topic. Read-only.",
            handler=lambda _args: self.mqtt_robot.telemetry(),
        ))
        self.registry.register(ToolSpec(
            name="robot_mqtt_publish",
            description="Publish a bounded robotics command to the configured MQTT topic. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string", "maxLength": 200}},
                "required": ["command"],
                "additionalProperties": False,
            },
            handler=lambda args: self.mqtt_robot.publish_command(str(args["command"])),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="robot_ros2_topics",
            description="List visible ROS2 topics and message types. Read-only.",
            handler=lambda _args: self.ros2_robot.list_topics(),
        ))
        self.registry.register(ToolSpec(
            name="robot_ros2_publish",
            description="Publish a bounded ROS2 message with a data field. Requires explicit confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "message_type": {"type": "string"},
                    "payload": {"type": "string", "maxLength": 4000},
                },
                "required": ["topic", "message_type", "payload"],
                "additionalProperties": False,
            },
            handler=lambda args: self.ros2_robot.publish(
                str(args["topic"]),
                str(args["message_type"]),
                str(args["payload"]),
            ),
            requires_confirmation=True,
            action=True,
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


    def _register_phase4_compat_tools(self) -> None:
        self.registry.register(ToolSpec(
            name="memory_recall",
            description="Search Jenefar's local layered memory and return matching records.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 1000},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "layers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query", "limit", "layers"],
                "additionalProperties": False,
            },
            handler=lambda args: [
                {
                    "id": hit.id,
                    "layer": hit.layer,
                    "kind": hit.kind,
                    "source": hit.source,
                    "title": hit.title,
                    "content": hit.content,
                    "score": hit.score,
                    "importance": hit.importance,
                }
                for hit in self.memory.recall(
                    str(args["query"]),
                    limit=int(args.get("limit", 8)),
                    include_procedures=True,
                ).hits
            ],
        ))
        self.registry.register(ToolSpec(
            name="memory_remember",
            description="Persist a fact, episode, or reusable procedure in Jenefar's local memory.",
            parameters={
                "type": "object",
                "properties": {
                    "layer": {"type": "string", "enum": ["episodic", "semantic", "procedural"]},
                    "title": {"type": "string", "maxLength": 300},
                    "content": {"type": "string", "maxLength": 12000},
                    "source": {"type": "string", "maxLength": 200},
                    "importance": {"type": "number", "minimum": 0, "maximum": 1},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "trigger_text": {"type": "string"},
                    "constraints": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["layer", "title", "content", "source", "importance", "tags", "steps", "trigger_text", "constraints"],
                "additionalProperties": False,
            },
            handler=self._memory_remember,
        ))
        self.registry.register(ToolSpec(
            name="event_catalog",
            description="List persistent Jenefar scheduled events and watchers.",
            handler=lambda _args: [
                {
                    "id": event.id,
                    "name": event.name,
                    "kind": event.kind,
                    "prompt": event.prompt,
                    "enabled": event.enabled,
                    "timezone": event.timezone,
                    "next_run_at": event.next_run_at,
                    "event_type": event.event_type,
                }
                for event in self.events.list()
            ],
        ))
        self.registry.register(ToolSpec(
            name="event_schedule_once",
            description="Schedule one persistent prompt for a future ISO-8601 time.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "prompt": {"type": "string"},
                    "run_at": {"type": "string"},
                },
                "required": ["name", "prompt", "run_at"],
                "additionalProperties": False,
            },
            handler=lambda args: self._event_schedule_once(args),
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="event_schedule_interval",
            description="Schedule a persistent repeating prompt; interval must be at least 60 seconds.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "prompt": {"type": "string"},
                    "every_seconds": {"type": "integer", "minimum": 60},
                    "start_at": {"type": ["string", "null"]},
                },
                "required": ["name", "prompt", "every_seconds", "start_at"],
                "additionalProperties": False,
            },
            handler=lambda args: self.events.schedule_interval(
                str(args["name"]),
                str(args["prompt"]),
                int(args["every_seconds"]),
                start_at=args.get("start_at"),
            ).__dict__,
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="event_schedule_daily",
            description="Schedule a persistent daily prompt at an IANA timezone.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "prompt": {"type": "string"},
                    "daily_time": {"type": "string"},
                    "timezone": {"type": "string"},
                    "start_at": {"type": ["string", "null"]},
                },
                "required": ["name", "prompt", "daily_time", "timezone", "start_at"],
                "additionalProperties": False,
            },
            handler=lambda args: self.events.schedule_daily(
                str(args["name"]),
                str(args["prompt"]),
                str(args["daily_time"]),
                timezone_name=str(args["timezone"]),
                start_at=args.get("start_at"),
            ).__dict__,
            requires_confirmation=True,
            action=True,
        ))
        self.registry.register(ToolSpec(
            name="event_watch",
            description="Watch for an application event type with optional equality filters and queue a Jenefar prompt.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "event_type": {"type": "string"},
                    "prompt": {"type": "string"},
                    "filters": {"type": "object"},
                },
                "required": ["name", "event_type", "prompt", "filters"],
                "additionalProperties": False,
            },
            handler=lambda args: self.events.watch(
                str(args["name"]),
                str(args["event_type"]),
                str(args["prompt"]),
                filters=dict(args.get("filters") or {}),
            ).__dict__,
            requires_confirmation=True,
            action=True,
        ))

    def _memory_remember(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = str(args["layer"]).strip().lower()
        title = str(args["title"])
        content = str(args["content"])
        source = str(args["source"])
        importance = float(args["importance"])
        tags = [str(x) for x in (args.get("tags") or [])]
        if layer == "episodic":
            self.memory.record_episode(title=title, content=content, source=source, importance=importance, tags=tags)
        elif layer == "semantic":
            self.memory.remember_fact(title=title, content=content, source=source, importance=importance, tags=tags)
        elif layer == "procedural":
            self.memory.save_procedure(
                name=title,
                trigger_text=str(args.get("trigger_text") or title),
                steps=[str(x) for x in (args.get("steps") or [content])],
                constraints=[str(x) for x in (args.get("constraints") or [])],
                source=source,
                importance=importance,
            )
        else:
            raise ValueError("layer must be episodic, semantic or procedural")
        return {"saved": True, "layer": layer, "title": title}

    def _event_schedule_once(self, args: dict[str, Any]) -> dict[str, Any]:
        event = self.events.schedule_once(
            str(args["name"]),
            str(args["prompt"]),
            str(args["run_at"]),
        )
        return event.__dict__

    def _connector_execute(
        self,
        connector: str,
        action: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        value = self.connectors.execute(connector, action, arguments)
        self.audit.record(
            "connector_executed",
            connector=connector,
            action=action,
            arguments=arguments,
        )
        return {
            "connector": connector,
            "action": action,
            "result": value,
        }

    @staticmethod
    def _whatsapp_script_path() -> str:
        return os.path.expanduser(
            os.getenv("JENEFAR_WHATSAPP_SCRIPT", "~/jenefar-tools/whatsapp_web.py")
        )

    def _whatsapp_open_web(self) -> dict[str, Any]:
        import shutil
        import subprocess

        script = self._whatsapp_script_path()
        if os.path.isfile(script):
            result = subprocess.run(
                ["python3", script, "open"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            return {
                "opened": result.returncode == 0,
                "method": "jenefar-whatsapp-helper",
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-2000:],
                "returncode": result.returncode,
            }

        opener = shutil.which("xdg-open")
        if not opener:
            raise RuntimeError("xdg-open is not available.")
        result = subprocess.run(
            [opener, "https://web.whatsapp.com/"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return {
            "opened": result.returncode == 0,
            "method": "xdg-open",
            "returncode": result.returncode,
        }

    def _whatsapp_send_web(self, args: dict[str, Any]) -> dict[str, Any]:
        import shutil
        import subprocess
        from urllib.parse import quote

        contact = str(args["contact"]).strip()
        message = str(args["message"]).strip()
        phone = str(args.get("phone") or "").strip()
        if not contact and not phone:
            raise ValueError("Provide a WhatsApp contact name or phone number.")

        script = self._whatsapp_script_path()
        if os.path.isfile(script):
            result = subprocess.run(
                ["python3", script, "send", contact, message],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr.strip() or result.stdout.strip() or "WhatsApp helper failed."
                )
            return {
                "sent": True,
                "method": "jenefar-whatsapp-helper",
                "contact": contact,
                "message": message,
                "stdout": result.stdout[-3000:],
            }

        if not phone:
            raise RuntimeError(
                "WhatsApp helper is not installed, and no phone number was provided for direct browser fallback."
            )

        normalized = "".join(ch for ch in phone if ch.isdigit())
        if normalized.startswith("0"):
            normalized = "91" + normalized[1:]
        elif len(normalized) == 10:
            normalized = "91" + normalized
        if len(normalized) < 10:
            raise ValueError("Invalid WhatsApp phone number.")

        opener = shutil.which("xdg-open")
        if not opener:
            raise RuntimeError("xdg-open is not available.")
        url = f"https://web.whatsapp.com/send?phone={normalized}&text={quote(message)}"
        result = subprocess.run(
            [opener, url],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return {
            "sent": False,
            "opened": result.returncode == 0,
            "method": "xdg-open",
            "phone": normalized,
            "message": message,
            "note": "WhatsApp Web opened with the message prefilled; the visible Send action is still required when the helper is unavailable.",
        }

    def _browser_play_youtube(self, query: str) -> dict[str, Any]:
        try:
            import shutil
            import subprocess
            ytdlp = shutil.which("yt-dlp")
            if ytdlp and internet_available():
                result = subprocess.run(
                    [ytdlp, "ytsearch1:" + query, "--get-id", "--no-playlist"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                video_id = next(
                    (line.strip() for line in result.stdout.splitlines() if line.strip()),
                    "",
                )
                if video_id:
                    from jenefar.automation.browser import open_url
                    return open_url("https://www.youtube.com/watch?v=" + video_id)
        except Exception:
            pass
        return play_youtube(query)

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

    def _desktop_observe(self, query: str, save: bool = False) -> dict[str, Any]:
        vision = self._get_screen_vision()
        result = vision.analyze(query)
        if save:
            frame = vision.capture(save=True)
            result["saved_path"] = frame.path
        self.audit.record("desktop_screen_observed", query=query, provider=result.get("provider", "unknown"))
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

    def schemas(
        self,
        *,
        allow_action_tools: bool = False,
        include_confirmation_tools: bool = True,
    ) -> list[dict[str, Any]]:
        return self.registry.openai_tools(
            include_confirmation_tools=include_confirmation_tools,
            include_action_tools=allow_action_tools,
        )

    def invoke(self, name: str, arguments: dict[str, Any], *, confirmed: bool = False) -> str:
        self._activity("thinking", f"Tool requested: {name}")
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
            self._activity(
                "waiting_approval",
                f"Approval required: {name} [{pending_id}]",
            )
            return json.dumps({
                "status": "approval_required",
                "pending_id": pending_id,
                "tool": name,
                "message": "Explicit user confirmation is required before this tool can execute.",
            })

        try:
            self._activity("thinking", f"Executing tool: {name}")
            value = spec.handler(arguments)
            self.audit.record("tool_executed", tool=name, arguments=arguments, result=value)
            self._activity("thinking", f"Tool result: {name} -> {str(value)[:1800]}")
            return json.dumps({"status": "ok", "result": value}, ensure_ascii=False, default=str)
        except Exception as exc:
            self.audit.record(
                "tool_error",
                tool=name,
                arguments=arguments,
                error=f"{type(exc).__name__}: {exc}",
            )
            self._activity(
                "error",
                f"Tool error: {name} -> {type(exc).__name__}: {exc}",
            )
            return json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"})

    def reject(self, pending_id: str) -> str:
        pending = self.pending.pop(pending_id, None)
        if pending is None:
            return json.dumps({"status": "error", "error": "Unknown or expired pending tool call."})
        self.audit.record("tool_rejected", pending_id=pending_id, tool=pending.name)
        self._activity("idle", f"Action denied: {pending.name}")
        return json.dumps({"status": "denied", "tool": pending.name})

    def approve(self, pending_id: str) -> str:
        pending = self.pending.pop(pending_id, None)
        if pending is None:
            return json.dumps({"status": "error", "error": "Unknown or expired pending tool call."})
        self.audit.record("tool_approved", pending_id=pending_id, tool=pending.name)
        self._activity("thinking", f"Approval granted: {pending.name}")
        return self.invoke(pending.name, pending.arguments, confirmed=True)
