from __future__ import annotations

from jenefar.agents.bugbounty.bugbounty import BugBountyAgent
from jenefar.agents.coding.python import PythonAgent
from jenefar.agents.coding.repository_agent import RepositoryAgent
from jenefar.agents.cybersecurity.cyber import CybersecurityAgent
from jenefar.agents.research.research import ResearchAgent
from jenefar.agents.robotics.robotics import RoboticsAgent
from jenefar.core.config import load_config
from jenefar.core.planner import Planner
from jenefar.core.router import AgentRouter
from jenefar.core.session import Session
from jenefar.memory.store import MemoryStore
from jenefar.core.state import JenefarState
from jenefar.critic.verifier import Verifier
from jenefar.tools.broker import ToolBroker
from jenefar.execution.audit import AuditLogger
from jenefar.execution.scope import ScopePolicy
from jenefar.voice.wakeword import WakeWord

class JenefarOrchestrator:
    def __init__(self):
        self.config = load_config()
        self.state = JenefarState.SLEEPING
        self.session = Session()
        self.memory = MemoryStore()
        self.planner = Planner()
        self.audit = AuditLogger(self.config.audit_log_path)
        self.scope = ScopePolicy(self.config.authorized_targets)
        self.tool_broker = ToolBroker(
            require_confirmation=self.config.require_confirmation_for_tools,
            audit=self.audit,
            scope=self.scope,
        )
        self.router = AgentRouter([
            RepositoryAgent(tool_broker=self.tool_broker),
            PythonAgent(tool_broker=self.tool_broker),
            CybersecurityAgent(tool_broker=self.tool_broker),
            BugBountyAgent(tool_broker=self.tool_broker),
            RoboticsAgent(tool_broker=self.tool_broker),
            ResearchAgent(tool_broker=self.tool_broker),
        ])
        self.verifier = Verifier()
        self.wakeword = WakeWord(self.config.wake_phrases)

    def run(self):
        print(f"[JENEFAR] {self.config.name} is running.")
        print("[JENEFAR] Sleeping. Say/type 'Hi Jenefar' or 'Hello Jenefar' to wake me.")
        print("[JENEFAR] Type 'exit' to quit.")
        print("[JENEFAR] Type 'approve <id>' only after reviewing a pending local tool action.")

        while True:
            try:
                raw = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[JENEFAR] Shutting down.")
                return

            lowered = raw.lower()
            if lowered == "exit":
                print("[JENEFAR] Goodbye.")
                return

            if lowered.startswith("approve "):
                pending_id = raw.split(maxsplit=1)[1].strip()
                if pending_id:
                    result = self.tool_broker.approve(pending_id)
                    print(f"Jenefar > {result}")
                    self.state = JenefarState.SLEEPING
                continue

            if self.state == JenefarState.WAITING_APPROVAL:
                print("[JENEFAR] A tool approval is pending. Use: approve <id>")
                continue

            if self.state == JenefarState.SLEEPING:
                if not self.wakeword.detect(raw):
                    print("[JENEFAR] (sleeping)")
                    continue
                self.state = JenefarState.AWAKE
                command = self.wakeword.remove_wake_phrase(raw)
                if not command:
                    print("[JENEFAR] Yes, I'm listening.")
                    continue
                print(f"Jenefar > {self.handle(command)}")
                continue

            if raw:
                print(f"Jenefar > {self.handle(raw)}")

    def handle(self, text: str) -> str:
        self.state = JenefarState.THINKING
        self.session.add("user", text)
        self.memory.remember_message(self.session.session_id, "user", text)
        retrieved = self.memory.search(text, limit=6)
        plan = self.planner.plan(text)
        result = self.router.dispatch(
            text,
            metadata={
                "session_id": self.session.session_id,
                "intent": plan.intent,
                "planned_agent": plan.agent,
                "planner_reason": plan.reason,
                "history": self.session.recent(8),
                "retrieved_memory": [
                    {"source": hit.source, "title": hit.title, "content": hit.content}
                    for hit in retrieved
                ],
            },
        )
        output = self.verifier.verify(text, result.content)
        self.session.add("assistant", output)
        self.memory.remember_message(self.session.session_id, "assistant", output)

        if result.metadata.get("provider") == "approval_required":
            self.state = JenefarState.WAITING_APPROVAL
        else:
            self.state = (
                JenefarState.SLEEPING
                if self.config.single_turn_sleep
                else JenefarState.AWAKE
            )
        return output
