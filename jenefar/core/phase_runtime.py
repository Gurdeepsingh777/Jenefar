from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from jenefar.avatar.viseme import text_to_visemes
from jenefar.core.autonomous import AutonomousTaskEngine
from jenefar.memory.lifecycle import MemoryLifecycle
from jenefar.research.citations import Citation, attach_citations
from jenefar.security.engagement import SecurityEngagement
from jenefar.voice.interaction import VoiceInteractionController
from jenefar.robotics.unified import UnifiedRobotController


class PhaseRuntime:
    """Runtime bridge that exposes the nine upgrade systems through one bounded API."""

    def __init__(self, *, data_root: str | Path = "data", tool_broker: Any | None = None) -> None:
        root = Path(data_root)
        self.tool_broker = tool_broker
        self.memory = MemoryLifecycle(root / "jenefar_memory.db")
        self.voice = VoiceInteractionController()
        self.security = SecurityEngagement(root / "security_engagement.json")
        self.robotics = UnifiedRobotController(
            serial=getattr(tool_broker, "robotics", None),
            mqtt=getattr(tool_broker, "mqtt_robot", None),
            ros2=getattr(tool_broker, "ros2_robot", None),
        )
        self._autonomous: AutonomousTaskEngine | None = None

    def configure_autonomous(
        self,
        *,
        planner: Callable[[str], list[dict[str, Any]]],
        executor: Callable[[dict[str, Any]], Any],
        verifier: Callable[[dict[str, Any], Any], bool],
        replanner: Callable[[str, list[Any]], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._autonomous = AutonomousTaskEngine(
            planner=planner,
            executor=executor,
            verifier=verifier,
            replanner=replanner,
        )

    def run_autonomous(self, task: str) -> dict[str, Any]:
        if self._autonomous is None:
            raise RuntimeError("Autonomous runtime is not configured.")
        return self._autonomous.run(task).as_dict()

    def remember_fact(self, key: str, value: str, *, confidence: float = .8, source: str = "user") -> dict[str, Any]:
        return self.memory.remember(key, value, confidence=confidence, source=source).__dict__

    def recall_fact(self, key: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        return [item.__dict__ for item in self.memory.recall(key, include_inactive=include_inactive)]

    def voice_listening(self) -> int:
        return self.voice.begin_listening()

    def voice_speaking(self) -> int:
        return self.voice.begin_speaking()

    def voice_interrupt(self) -> dict[str, Any]:
        self.voice.interrupt()
        return self.voice.snapshot()

    def voice_snapshot(self) -> dict[str, Any]:
        return self.voice.snapshot()

    def avatar_visemes(self, text: str) -> list[dict[str, Any]]:
        return [frame.__dict__ for frame in text_to_visemes(text)]

    def research_citations(self, claims: list[str], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations = [
            Citation(
                source=str(item.get("source", "")),
                title=str(item.get("title", "")),
                locator=str(item.get("locator", "")),
                claim=str(item.get("claim", "")),
            )
            for item in sources
        ]
        return attach_citations(claims, citations)

    def security_start(self, name: str, scope: list[str]) -> dict[str, Any]:
        return self.security.start(name, scope)

    def security_finding(
        self,
        title: str,
        severity: str,
        target: str,
        evidence: str,
        recommendation: str,
    ) -> dict[str, Any]:
        return self.security.add_finding(title, severity, target, evidence, recommendation)

    def security_report(self) -> dict[str, Any]:
        return self.security.report()

    def robot_status(self) -> dict[str, Any]:
        return self.robotics.status()

    def robot_command(self, command: str, *, transport: str = "auto", argument: str = "") -> Any:
        return self.robotics.command(command, transport=transport, argument=argument)

    def coding_workflow(self, workspace: Any | None = None) -> Any:
        from jenefar.coding.workflow import CodingWorkflow
        workspace = workspace or getattr(self.tool_broker, "workspace", None)
        if workspace is None:
            raise RuntimeError("Coding workspace is not available.")
        return CodingWorkflow(workspace)

    def vision_loop(self, vision: Any | None = None, *, max_actions: int = 8) -> Any:
        from jenefar.vision.agent_loop import VisionAgentLoop
        vision = vision or getattr(self.tool_broker, "screen_vision", None)
        if vision is None and self.tool_broker is not None and hasattr(self.tool_broker, "_get_screen_vision"):
            vision = self.tool_broker._get_screen_vision()
        if vision is None:
            raise RuntimeError("Vision backend is not available.")
        return VisionAgentLoop(vision, max_actions=max_actions)

    def autonomous_status(self) -> dict[str, Any]:
        return {"configured": self._autonomous is not None, "max_steps": 50}

    def snapshot(self) -> dict[str, Any]:
        return {
            "memory": {"active_facts": len(self.memory.recall("__runtime_probe__", include_inactive=False))},
            "voice": self.voice.snapshot(),
            "avatar": {"viseme_engine": True},
            "vision": {"agent_loop": True},
            "coding": {"workflow": True},
            "research": {"citations": True},
            "security": self.security.report(),
            "robotics": self.robotics.status(),
            "integrated_backends": {
                "coding_workspace": getattr(self.tool_broker, "workspace", None) is not None,
                "vision_backend": getattr(self.tool_broker, "screen_vision", None) is not None,
                "security_gateway": getattr(self.tool_broker, "security", None) is not None,
                "robot_transports": self.robotics.status(),
            },
            "autonomous": self.autonomous_status(),
        }


__all__ = ["PhaseRuntime"]
