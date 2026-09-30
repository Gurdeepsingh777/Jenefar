from __future__ import annotations

import inspect
import json
from jenefar.agents.automation.desktop import AutomationAgent
from jenefar.agents.automation.gui import VisionGUIAgent
from jenefar.agents.bugbounty.bugbounty import BugBountyAgent
from jenefar.agents.coding.python import PythonAgent
from jenefar.agents.coding.repository_agent import RepositoryAgent
from jenefar.agents.coding.local_development import LocalDevelopmentAgent
from jenefar.agents.cybersecurity.cyber import CybersecurityAgent
from jenefar.agents.cybersecurity.kali import KaliSecurityAgent
from jenefar.agents.research.research import ResearchAgent
from jenefar.agents.robotics.robotics import RoboticsAgent
from jenefar.agents.utility import UtilityAgent
from jenefar.core.config import load_config
from jenefar.core.planner import Planner
from jenefar.core.router import AgentRouter
from jenefar.core.session import Session
from jenefar.memory.store import MemoryStore
from jenefar.memory.graph import KnowledgeGraph
from jenefar.memory.advanced import AdvancedMemory
from jenefar.events.engine import EventEngine
from jenefar.evaluation.loop import EvaluationLoop
from jenefar.evaluation.trace import ExecutionTrace, TraceStore
from jenefar.core.self_healing import SelfHealingRuntime
from jenefar.core.state import JenefarState
from jenefar.critic.verifier import Verifier
from jenefar.tools.broker import ToolBroker
from jenefar.execution.audit import AuditLogger
from jenefar.execution.scope import ScopePolicy
from jenefar.voice.wakeword import WakeWord
from jenefar.capabilities.store import CapabilityStore
from jenefar.offline.connectivity import internet_available
from jenefar.skills.manager import SkillManager

class JenefarOrchestrator:
    def __init__(self, avatar=None):
        self.config = load_config()
        self.state = JenefarState.SLEEPING
        self.session = Session()
        self.memory = MemoryStore()
        self.memory_engine = AdvancedMemory(self.memory)
        self.graph = KnowledgeGraph(self.memory.path)
        self.events = EventEngine()
        self.capabilities = CapabilityStore()
        self.skills = SkillManager()
        self.evaluator = EvaluationLoop()
        self.trace_store = TraceStore()
        self.self_healing = SelfHealingRuntime()
        self.planner = Planner(skills=self.skills)
        self.audit = AuditLogger(self.config.audit_log_path)
        self.scope = ScopePolicy(self.config.authorized_targets)
        self.avatar = avatar
        self.tool_broker = ToolBroker(
            require_confirmation=self.config.require_confirmation_for_tools,
            audit=self.audit,
            scope=self.scope,
            skills=self.skills,
            memory=self.memory_engine,
            events=self.events,
            event_handler=self._handle_scheduled_event,
            activity_handler=self._avatar_activity,
        )
        self.router = AgentRouter([
            RepositoryAgent(tool_broker=self.tool_broker),
            LocalDevelopmentAgent(tool_broker=self.tool_broker),
            VisionGUIAgent(tool_broker=self.tool_broker),
            AutomationAgent(tool_broker=self.tool_broker),
            KaliSecurityAgent(tool_broker=self.tool_broker),
            PythonAgent(tool_broker=self.tool_broker),
            CybersecurityAgent(tool_broker=self.tool_broker),
            BugBountyAgent(tool_broker=self.tool_broker),
            RoboticsAgent(tool_broker=self.tool_broker),
            UtilityAgent(tool_broker=self.tool_broker),
            ResearchAgent(tool_broker=self.tool_broker),
        ])
        self.verifier = Verifier()
        self.wakeword = WakeWord(self.config.wake_phrases)
        self.pending_approval_workflows: dict[str, dict] = {}
        self.offline_notice_open = False

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

            if lowered == "cancel":
                self.pending_approval_workflows.clear()
                self.tool_broker.pending.clear()
                self.state = JenefarState.SLEEPING
                print("[JENEFAR] Pending approval cancelled.")
                continue

            if lowered.startswith("approve "):
                pending_id = raw.split(maxsplit=1)[1].strip()
                if pending_id:
                    result = self._approve_pending(pending_id)
                    print(f"Jenefar > {result}")
                continue

            if self.state == JenefarState.WAITING_APPROVAL:
                print("[JENEFAR] A tool approval is pending. Use: approve <id>")
                continue

            if self.state == JenefarState.SLEEPING:
                matched_phrase = self.wakeword.matched_phrase(raw)
                if matched_phrase is None:
                    print("[JENEFAR] (sleeping)")
                    continue
                self.state = JenefarState.AWAKE
                command = self.wakeword.remove_wake_phrase(raw)
                response_language = (
                    "Hinglish" if matched_phrase == "hello jenefar" else None
                )
                if not command:
                    if response_language == "Hinglish":
                        print("[JENEFAR] Haan, boliye. Main sun rahi hoon.")
                    else:
                        print("[JENEFAR] Yes, I'm listening.")
                    continue
                print(
                    f"Jenefar > {self.handle(command, response_language=response_language)}"
                )
                continue

            if raw:
                print(f"Jenefar > {self.handle(raw)}")

    def handle(
        self,
        text: str,
        response_language: str | None = None,
        *,
        source: str = "user",
        event_id: int | None = None,
    ) -> str:
        trace = ExecutionTrace(
            session_id=self.session.session_id,
            task=text,
            source=source,
            event_id=event_id,
        )
        self.state = JenefarState.THINKING
        self._avatar_state("thinking", "Processing your request…")
        self.session.add("user", text)
        self.memory_engine.record_message(
            self.session.session_id,
            "user",
            text,
            importance=0.55 if source == "user" else 0.5,
        )
        self.graph.learn_text(text)
        try:
            if self._is_local_time_query(text):
                output = self._local_time_response(text, response_language)
                self.session.add("assistant", output)
                self.memory_engine.record_message(
                    self.session.session_id,
                    "assistant",
                    output,
                    importance=0.45,
                )
                self.state = JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
                self._avatar_state("speaking", output)
                return output

            recall = self.memory_engine.recall(text, limit=8)
            graph_hits = self.graph.search(text.split()[0] if text.split() else text, limit=8)
            plan = self.planner.plan(text)
            task_plan = self.planner.task_planner.build(text, plan.intent, plan.agent)
            trace.intent = plan.intent
            trace.planned_agent = plan.agent
            trace.planner_confidence = plan.confidence
            trace.model_role = self._model_role_for_plan(plan)
            connected = internet_available()
            trace.connectivity = "online" if connected else "offline"
            online_task = any(marker in text.lower() for marker in (
                "youtube", "online", "download", "internet", "web search",
                "search the web", "github", "recognize this song",
            ))
            if not connected and online_task:
                self.offline_notice_open = True
            runtime = {
                "connectivity": "online" if connected else "offline",
                "offline_limitations": [
                    "web search and remote downloads",
                    "YouTube",
                    "online song recognition",
                    "live GitHub retrieval",
                ] if not connected else [],
            }
            dispatch_metadata = {
                "session_id": self.session.session_id,
                "trace_id": trace.trace_id,
                "intent": plan.intent,
                "planned_agent": plan.agent,
                "planner_reason": plan.reason,
                "planner_confidence": plan.confidence,
                "task_plan": task_plan.as_dict() | {"prompt_text": task_plan.prompt_text()},
                "model_role": trace.model_role,
                "response_language": response_language,
                "source": source,
                "event_id": event_id,
                "runtime": runtime,
                "capabilities": self.capabilities.list(),
                "skills": [item for item in self.skills.list() if item.get("enabled")],
                "history": self.session.recent(8),
                "retrieved_memory": [
                    {"source": hit.source, "title": hit.title, "content": hit.content, "layer": hit.layer, "score": hit.score}
                    for hit in recall.hits
                ],
                "procedural_memory": list(recall.procedures),
                "knowledge_graph": [
                    {"subject": relation.subject, "predicate": relation.predicate, "object": relation.object}
                    for relation in graph_hits
                ],
            }
            self._avatar_activity(
                "thinking",
                f"Agent selected: {plan.agent} | intent={plan.intent}",
            )
            result = self.self_healing.run(
                "agent_dispatch",
                lambda: self.router.dispatch(text, metadata=dispatch_metadata),
                metadata={
                    "approval_required": False,
                    "security_action": plan.agent in {"kali", "cybersecurity", "bugbounty"},
                },
            )
            trace.metadata["self_healing"] = {
                "retries": self.self_healing.health.retries,
                "consecutive_failures": self.self_healing.health.consecutive_failures,
            }
            trace.actual_agent = result.agent
            self._avatar_activity(
                "thinking",
                f"Agent completed: {result.agent}",
            )
            trace.provider = str(result.metadata.get("provider", ""))
            for pending in result.metadata.get("pending_tools", []) or []:
                trace.add_tool_call(
                    name=str(pending.get("tool", "unknown")),
                    status="approval_required",
                    approval_required=True,
                )
            output = self.verifier.verify(text, result.content)
            if result.metadata.get("provider") and result.metadata.get("model"):
                provider_label = (
                    f"\n[Model: {result.metadata.get('provider')} / "
                    f"{result.metadata.get('model')}]"
                )
                output = output + provider_label
            verification = {
                "passed": bool(output and output.strip()),
                "verifier": self.verifier.__class__.__name__,
            }
            awaiting = result.metadata.get("provider") in {"approval_required", "local_approval_required"}
            trace.finish(status="awaiting_approval" if awaiting else "success", provider=trace.provider, verification=verification)
            self.session.add("assistant", output)
            self.memory_engine.record_message(
                self.session.session_id,
                "assistant",
                output,
                importance=0.5,
            )
            self.graph.learn_text(output)
            if len(self.session.messages) % 6 == 0:
                self.memory_engine.consolidate_messages(
                    self.session.session_id,
                    self.session.recent(12),
                    importance=0.72,
                )
            self.evaluator.evaluate(
                text,
                output,
                provider=trace.provider,
                trace=trace.as_dict(),
            )
            self.trace_store.append(trace)
            if awaiting:
                self._register_pending_workflow(text, result, response_language=response_language)
                self.state = JenefarState.WAITING_APPROVAL
                self._avatar_state("waiting_approval", output)
            else:
                self.state = JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
                self._avatar_state("speaking", output)
            return output
        except Exception as exc:
            trace.add_error(f"{type(exc).__name__}: {exc}")
            trace.finish(status="error", provider="error", verification={"passed": False})
            self.trace_store.append(trace)
            self.evaluator.evaluate(text, str(exc), provider="error", trace=trace.as_dict())
            self.state = JenefarState.SLEEPING
            self._avatar_state("error", str(exc))
            return f"Jenefar runtime error: {type(exc).__name__}: {exc}"

    @staticmethod
    def _is_local_time_query(text: str) -> bool:
        lowered = text.lower().strip()
        phrases = (
            "what time", "current time", "time kya", "abhi time",
            "kitne baje", "kitna time", "clock check", "laptop me time",
            "laptop ka time", "computer ka time", "system time",
            "today's date", "date today", "aaj ki date",
        )
        return any(phrase in lowered for phrase in phrases)

    def _local_time_response(self, text: str, response_language: str | None = None) -> str:
        payload = self.tool_broker._local_time()
        if str(response_language or "").lower() == "hinglish" or any(
            word in text.lower() for word in ("kya", "hai", "batao", "bata", "abhi", "laptop")
        ):
            return (
                f"Abhi aapke laptop ka local time {payload['time']} hai, "
                f"{payload['date']} ({payload['timezone']})."
            )
        return f"The current laptop time is {payload['time']} on {payload['date']} ({payload['timezone']})."

    @staticmethod
    def _model_role_for_plan(plan) -> str:
        from jenefar.core.model_router import ModelRouter
        return ModelRouter().role_for_intent(plan.intent, plan.agent)

    def _avatar_activity(self, state: str, text: str = "") -> None:
        if self.avatar is not None:
            self.avatar.publish(state, text)

    def _avatar_state(self, state: str, text: str = "") -> None:
        self._avatar_activity(state, text)

    def _register_pending_workflow(
        self,
        task: str,
        result,
        response_language: str | None = None,
    ) -> None:
        pending_tools = result.metadata.get("pending_tools", [])
        if not pending_tools:
            return
        workflow = {
            "task": task,
            "agent": result.agent,
            "response_language": response_language,
            "task_plan_text": self.planner.task_planner.build(
                task,
                self.planner.plan(task).intent,
                result.agent,
            ).prompt_text(),
            "remaining": {str(item["pending_id"]) for item in pending_tools},
            "results": [],
        }
        for item in pending_tools:
            self.pending_approval_workflows[str(item["pending_id"])] = workflow

    def _approve_pending(self, pending_id: str) -> str:
        workflow = self.pending_approval_workflows.get(pending_id)
        raw_result = self.tool_broker.approve(pending_id)

        if workflow is None:
            self.state = JenefarState.SLEEPING
            return raw_result

        workflow["remaining"].discard(pending_id)
        try:
            parsed = json.loads(raw_result)
        except json.JSONDecodeError:
            parsed = {"result": raw_result}

        tool_name = parsed.get("tool", "unknown")
        workflow["results"].append({
            "tool": tool_name,
            "result": parsed.get("result", parsed),
        })
        self.pending_approval_workflows.pop(pending_id, None)

        if workflow["remaining"]:
            self.state = JenefarState.WAITING_APPROVAL
            remaining = ", ".join(sorted(workflow["remaining"]))
            return f"Tool approval completed. Remaining approval id(s): {remaining}"

        agent = self.router.agent_by_name(workflow["agent"])
        if agent is None or not hasattr(agent, "continue_after_tools"):
            self.state = JenefarState.SLEEPING
            return raw_result

        continue_kwargs = {
            "continue_tools": bool(getattr(agent, "use_tools", False)),
            "task_plan_text": str(workflow.get("task_plan_text") or ""),
        }
        if workflow.get("response_language"):
            continue_kwargs["response_language"] = workflow["response_language"]
        signature = inspect.signature(agent.continue_after_tools)
        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        filtered_kwargs = (
            continue_kwargs
            if accepts_var_kwargs
            else {
                key: value
                for key, value in continue_kwargs.items()
                if key in signature.parameters
            }
        )
        final_result = agent.continue_after_tools(
            workflow["task"],
            workflow["results"],
            **filtered_kwargs,
        )
        pending_tools = final_result.metadata.get("pending_tools", [])
        if pending_tools:
            workflow["remaining"] = {
                str(item["pending_id"])
                for item in pending_tools
                if item.get("pending_id")
            }
            workflow["results"].append({
                "tool": "continuation",
                "result": final_result.content,
            })
            for item in pending_tools:
                self.pending_approval_workflows[str(item["pending_id"])] = workflow
            self.state = JenefarState.WAITING_APPROVAL
            ids = ", ".join(sorted(workflow["remaining"]))
            return final_result.content + (f" Remaining approval id(s): {ids}." if ids else "")

        output = self.verifier.verify(workflow["task"], final_result.content)
        self.session.add("assistant", output)
        self.memory_engine.record_message(
            self.session.session_id,
            "assistant",
            output,
            importance=0.55,
        )
        self.state = JenefarState.SLEEPING
        return output

    def _handle_scheduled_event(self, prompt: str, event) -> str:
        return self.handle(
            prompt,
            source="scheduler",
            event_id=getattr(event, "id", None),
        )
