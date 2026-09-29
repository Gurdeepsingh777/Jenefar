from __future__ import annotations

from typing import Any

from jenefar.automation.browser import open_url, play_youtube, first_mp3_in_folder
from jenefar.execution.scope import ScopePolicy
from jenefar.research.sources import fetch_github_repository, fetch_url
from jenefar.offline.connectivity import internet_available


class ConnectorManager:
    """Universal gateway over trusted connector adapters.

    Connectors are registered programmatically and expose a small manifest plus
    bounded actions. New service integrations can be added without changing the
    core orchestrator.
    """

    def __init__(
        self,
        *,
        workspace=None,
        desktop=None,
        screen_vision=None,
        robotics=None,
        mqtt_robot=None,
        ros2_robot=None,
        security=None,
    ) -> None:
        from jenefar.connectors.base import Connector, ConnectorAction, ConnectorManifest

        self._connectors: dict[str, Connector] = {}
        self.scope = security.scope if security is not None else ScopePolicy()
        self._register_builtin(
            Connector,
            ConnectorAction,
            ConnectorManifest,
            workspace=workspace,
            desktop=desktop,
            robotics=robotics,
            mqtt_robot=mqtt_robot,
            ros2_robot=ros2_robot,
            security=security,
        )

    def _register_builtin(
        self,
        Connector,
        ConnectorAction,
        ConnectorManifest,
        *,
        workspace,
        desktop,
        robotics,
        mqtt_robot,
        ros2_robot,
        security,
    ) -> None:
        if desktop is not None:
            handlers = {
                "screen_size": lambda _args: desktop.screen_size(),
                "hotkey": lambda args: desktop.hotkey([str(item) for item in args["keys"]]),
                "scroll": lambda args: desktop.scroll(int(args["clicks"])),
            }
            actions = [
                ConnectorAction("screen_size", "Return current screen dimensions."),
                ConnectorAction("hotkey", "Press a bounded keyboard shortcut.", True),
                ConnectorAction("scroll", "Scroll the desktop by a bounded amount.", True),
            ]
            if screen_vision is not None:
                handlers.update({
                    "observe": lambda args: screen_vision.analyze(str(args["query"])),
                    "find_element": lambda args: screen_vision.locate(str(args["query"])),
                    "click_element": lambda args: screen_vision.locate_and_click(str(args["query"])),
                    "type_into_element": lambda args: screen_vision.locate_and_type(
                        str(args["query"]),
                        str(args["text"]),
                    ),
                })
                actions.extend([
                    ConnectorAction("observe", "Analyze the current screen semantically.", True),
                    ConnectorAction("find_element", "Locate a semantic UI element.", True),
                    ConnectorAction("click_element", "Click a semantic UI element.", True),
                    ConnectorAction("type_into_element", "Type into a semantic input.", True),
                ])
            self.register(
                Connector(
                    ConnectorManifest(
                        name="desktop",
                        version="1.0",
                        description="Semantic desktop and GUI control adapter.",
                        online_required=False,
                        actions=tuple(actions),
                    ),
                    handlers,
                )
            )

        if workspace is not None:
            self.register(
                Connector(
                    ConnectorManifest(
                        name="workspace",
                        version="1.0",
                        description="Authorized local workspace read operations.",
                        online_required=False,
                        actions=(
                            ConnectorAction("list", "List an authorized directory."),
                            ConnectorAction("inspect", "Inspect an authorized local file."),
                        ),
                    ),
                    {
                        "list": lambda args: workspace.list_directory(
                            str(args["path"]),
                            int(args.get("max_items", 200)),
                        ),
                        "inspect": lambda args: workspace.inspect_file(
                            str(args["path"]),
                            int(args.get("max_bytes", 200000)),
                        ),
                    },
                )
            )

        self.register(
            Connector(
                ConnectorManifest(
                    name="media",
                    version="1.0",
                    description="Local media playback adapter using the configured VLC helper.",
                    online_required=False,
                    actions=(
                        ConnectorAction("play_first_mp3", "Play the first MP3 under a local folder.", True),
                    ),
                ),
                {
                    "play_first_mp3": lambda args: first_mp3_in_folder(str(args["path"])),
                },
            )
        )

        self.register(
            Connector(
                ConnectorManifest(
                    name="browser",
                    version="1.0",
                    description="Open public URLs or YouTube searches in the preferred browser.",
                    online_required=True,
                    actions=(
                        ConnectorAction("open_url", "Open a public URL.", True),
                        ConnectorAction("youtube", "Open the first matching YouTube result.", True),
                    ),
                ),
                {
                    "open_url": lambda args: open_url(str(args["url"])),
                    "youtube": lambda args: play_youtube(str(args["query"])),
                },
            )
        )

        self.register(
            Connector(
                ConnectorManifest(
                    name="web",
                    version="1.0",
                    description="Read public HTTP(S) resources without executing remote content.",
                    online_required=True,
                    actions=(
                        ConnectorAction("fetch_url", "Fetch a public URL as text."),
                    ),
                ),
                {
                    "fetch_url": lambda args: self._fetch_url(args),
                },
            )
        )

        self.register(
            Connector(
                ConnectorManifest(
                    name="github",
                    version="1.0",
                    description="Read public GitHub repositories and files.",
                    online_required=True,
                    actions=(
                        ConnectorAction("fetch_repository", "Fetch public repository text files."),
                    ),
                ),
                {
                    "fetch_repository": lambda args: self._fetch_github(args),
                },
            )
        )

        if robotics is not None:
            self.register(
                Connector(
                    ConnectorManifest(
                        name="robotics",
                        version="1.0",
                        description="Bounded robotics discovery and command adapters.",
                        online_required=False,
                        actions=(
                            ConnectorAction("list_ports", "List visible serial ports."),
                            ConnectorAction("command", "Send a bounded serial robot command.", True),
                        ),
                    ),
                    {
                        "list_ports": lambda _args: robotics.list_ports(),
                        "command": lambda args: robotics.command(
                            str(args["command"]),
                            str(args.get("argument", "")),
                        ),
                    },
                )
            )

        if mqtt_robot is not None:
            self.register(
                Connector(
                    ConnectorManifest(
                        name="mqtt",
                        version="1.0",
                        description="Configured MQTT robotics telemetry and command adapter.",
                        online_required=False,
                        actions=(
                            ConnectorAction("telemetry", "Read latest configured telemetry."),
                            ConnectorAction("publish", "Publish a bounded robot command.", True),
                        ),
                    ),
                    {
                        "telemetry": lambda _args: mqtt_robot.telemetry(),
                        "publish": lambda args: mqtt_robot.publish_command(str(args["command"])),
                    },
                )
            )

        if ros2_robot is not None:
            self.register(
                Connector(
                    ConnectorManifest(
                        name="ros2",
                        version="1.0",
                        description="Configured ROS2 topic discovery and bounded publication.",
                        online_required=False,
                        actions=(
                            ConnectorAction("topics", "List visible ROS2 topics."),
                            ConnectorAction("publish", "Publish a bounded ROS2 message.", True),
                        ),
                    ),
                    {
                        "topics": lambda _args: ros2_robot.list_topics(),
                        "publish": lambda args: ros2_robot.publish(
                            str(args["topic"]),
                            str(args["message_type"]),
                            str(args["payload"]),
                        ),
                    },
                )
            )

        if security is not None:
            self.register(
                Connector(
                    ConnectorManifest(
                        name="security",
                        version="1.0",
                        description="Scoped security execution through the existing security boundary.",
                        online_required=False,
                        actions=(
                            ConnectorAction("scope_check", "Check a target against authorized security scope."),
                            ConnectorAction("scan", "Run a constrained security profile.", True),
                        ),
                    ),
                    {
                        "scope_check": lambda args: {
                            "allowed": self.scope.allows(str(args["target"])),
                            "message": self.scope.explain(str(args["target"])),
                        },
                        "scan": lambda args: security.run(
                            tool=str(args["tool"]),
                            target=str(args["target"]),
                            timeout=int(args.get("timeout", 120)),
                        ),
                    },
                )
            )

    def register(self, connector) -> None:
        name = connector.manifest.name.strip().lower()
        if not name:
            raise ValueError("Connector name cannot be empty.")
        self._connectors[name] = connector

    def list(self) -> list[dict[str, Any]]:
        return [
            connector.manifest.as_dict()
            for connector in sorted(
                self._connectors.values(),
                key=lambda item: item.manifest.name,
            )
        ]

    def status(self, name: str) -> dict[str, Any]:
        connector = self.get(name)
        available = (
            True
            if not connector.manifest.online_required
            else internet_available()
        )
        return {
            **connector.manifest.as_dict(),
            "available": available,
        }

    def get(self, name: str):
        key = str(name).strip().lower()
        try:
            return self._connectors[key]
        except KeyError as exc:
            raise KeyError(f"Unknown connector: {key}") from exc

    def execute(self, name: str, action: str, arguments: dict[str, Any]) -> Any:
        connector = self.get(name)
        if connector.manifest.online_required and not internet_available():
            raise ConnectionError(
                f"Connector '{connector.manifest.name}' requires an internet connection."
            )
        return connector.execute(action, arguments)

    def action_requires_confirmation(self, name: str, action: str) -> bool:
        return connector_action_requires_confirmation(self.get(name), action)

    @staticmethod
    def _fetch_url(args: dict[str, Any]) -> dict[str, Any]:
        doc = fetch_url(
            str(args["url"]),
            max_bytes=int(args.get("max_bytes", 2000000)),
        )
        return {
            "source": doc.source,
            "title": doc.title,
            "content": doc.content[:100000],
            "metadata": doc.metadata,
        }

    @staticmethod
    def _fetch_github(args: dict[str, Any]) -> list[dict[str, Any]]:
        docs = fetch_github_repository(
            str(args["repository"]),
            ref=str(args.get("ref", "main")),
            paths=[str(args["path"])] if str(args.get("path", "")).strip() else None,
            max_files=min(int(args.get("max_files", 10)), 20),
        )
        return [
            {
                "source": doc.source,
                "title": doc.title,
                "content": doc.content[:50000],
                "metadata": doc.metadata,
            }
            for doc in docs
        ]


def connector_action_requires_confirmation(connector, action: str) -> bool:
    return connector.action(action).requires_confirmation


__all__ = ["ConnectorManager", "connector_action_requires_confirmation"]
