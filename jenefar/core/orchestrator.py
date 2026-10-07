from __future__ import annotations

import inspect
import os
import time
import json
from typing import Any
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
from jenefar.core.cancellation import CancellationToken
from jenefar.core.task_lifecycle import TaskLifecycle
from jenefar.core.state import JenefarState
from jenefar.critic.verifier import Verifier
from jenefar.tools.broker import ToolBroker
from jenefar.execution.audit import AuditLogger
from jenefar.execution.scope import ScopePolicy
from jenefar.voice.wakeword import WakeWord
from jenefar.capabilities.store import CapabilityStore
from jenefar.offline.connectivity import internet_available
from jenefar.skills.manager import SkillManager
from jenefar.evaluation.runtime_status import build_runtime_snapshot
from jenefar.core.production_runtime import ProductionRuntime
from jenefar.core.phase_runtime import PhaseRuntime

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
        self.runtime_context: dict[str, Any] = {"state": "idle"}
        self._active_cancel_token: CancellationToken | None = None
        self.task_lifecycle = TaskLifecycle()
        self.production = ProductionRuntime()
        self.phase_runtime = PhaseRuntime(data_root="data", tool_broker=self.tool_broker)

    @staticmethod
    def _execution_budget_seconds(model_role: str, agent: str) -> float:
        role = str(model_role or "fast").strip().lower()
        agent_name = str(agent or "agent").strip().lower().replace("-", "_")
        agent_key = f"JENEFAR_AGENT_TIMEOUT_{agent_name.upper()}"
        role_key = f"JENEFAR_AGENT_TIMEOUT_{role.upper()}"
        raw = os.getenv(agent_key, os.getenv(role_key, os.getenv("JENEFAR_AGENT_TIMEOUT_SECONDS", "60")))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 60.0
        return min(max(value, 10.0), 300.0)

    def cancel_active_task(self, reason: str = "cancelled by user") -> dict[str, Any]:
        token = self._active_cancel_token
        active = self.task_lifecycle.active()
        if token is None or token.cancelled or active is None:
            return {"cancelled": False, "active": False, "reason": "no active task"}
        changed = token.cancel(reason)
        self.task_lifecycle.transition(active["task_id"], "cancelling", reason=token.reason)
        self.runtime_context.update({"state": "cancelling", "last_event": token.reason})
        return {"cancelled": changed, "active": True, "task_id": active["task_id"], "reason": token.reason}
    def run_autonomous_task(self, text: str) -> dict[str, Any]:
        """Execute the hierarchical task plan through the bounded autonomous runtime."""
        plan = self.planner.plan(text)
        task_plan = self.planner.task_planner.build(text, plan.intent, plan.agent)
        steps = [step.as_dict() for step in task_plan.steps]
        base_metadata = {
            "session_id": self.session.session_id,
            "intent": plan.intent,
            "planned_agent": plan.agent,
            "planner_confidence": plan.confidence,
            "task_plan": task_plan.as_dict(),
            "response_language": "Hinglish",
            "source": "autonomous",
            "capabilities": self.capabilities.list(),
            "skills": [item for item in self.skills.list() if item.get("enabled")],
        }

        def execute(step):
            result = self.router.dispatch(
                str(step.get("instruction") or step.get("title") or text),
                metadata=base_metadata | {"autonomous_step": step},
            )
            return {"agent": result.agent, "content": result.content, "metadata": result.metadata}

        def verify(step, result):
            return bool(str(result.get("content") or "").strip())

        def replan(_task, history):
            completed = {item.step_id for item in history if item.status == "completed"}
            return [step for step in steps if step.get("id") not in completed]

        self.phase_runtime.configure_autonomous(
            planner=lambda _task: list(steps),
            executor=execute,
            verifier=verify,
            replanner=replan,
        )
        return self.phase_runtime.run_autonomous(text)

    def runtime_status(self) -> dict[str, Any]:
        """Return a live, credential-safe runtime snapshot for the UI."""
        from jenefar.core.provider_pool import ProviderPool
        snapshot = build_runtime_snapshot(
            runtime_context=self.runtime_context,
            self_healing=self.self_healing,
            trace_store=self.trace_store,
            provider_pool=ProviderPool(),
        )
        snapshot["tasks"] = self.task_lifecycle.snapshot()
        snapshot["production"] = self.production.snapshot()
        snapshot["phase_runtime"] = self.phase_runtime.snapshot()
        return snapshot

    def runtime_tasks(
        self,
        *,
        search: str = "",
        state: str = "",
        agent: str = "",
        provider: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return filtered persistent task history for the runtime console."""
        return self.task_lifecycle.query_history(
            search=search,
            state=state,
            agent=agent,
            provider=provider,
            limit=limit,
        )

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
        # Jenefar's user-facing runtime is intentionally Roman Hinglish-first.
        # Keep the language stable even when a caller omits the preference.
        response_language = response_language or "Hinglish"
        self.phase_runtime.voice_listening()

        pending_reply = self._handle_conversational_confirmation(
            text,
            response_language=response_language,
        )
        if pending_reply is not None:
            self._avatar_state("speaking", pending_reply)
            return pending_reply
        trace = ExecutionTrace(
            session_id=self.session.session_id,
            task=text,
            source=source,
            event_id=event_id,
        )
        if self.task_lifecycle.admit(trace.trace_id, text) is None:
            return "Jenefar abhi ek task execute kar rahi hai. Pehle current task complete ya cancel hone dein."
        self.task_lifecycle.transition(trace.trace_id, "running")
        self.production.task_started(trace.trace_id, text, agent="pending")
        self.state = JenefarState.THINKING
        self._avatar_state("thinking", "")
        self.session.add("user", text)
        self.memory_engine.record_message(
            self.session.session_id,
            "user",
            text,
            importance=0.55 if source == "user" else 0.5,
        )
        self.production.remember(text, kind="episodic", importance=0.55 if source == "user" else 0.5, provenance="conversation")
        self.graph.learn_text(text)
        try:
            direct_window = self._direct_window_transfer(text)
            if direct_window:
                from jenefar.voice.speech import devanagari_to_roman
                output = devanagari_to_roman(direct_window)
                self.session.add("assistant", output)
                self.memory_engine.record_message(
                    self.session.session_id,
                    "assistant",
                    output,
                    importance=0.5,
                )
                self.state = JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
                self._avatar_state("speaking", output)
                self.production.remember(output, kind="episodic", importance=0.5, provenance="assistant")
                self.production.task_finished(trace.trace_id, state="completed", agent=trace.actual_agent or "direct")
                return output

            direct_screen = self._direct_screen_read(text)
            if direct_screen:
                from jenefar.voice.speech import devanagari_to_roman
                output = devanagari_to_roman(direct_screen)
                self.session.add("assistant", output)
                self.memory_engine.record_message(
                    self.session.session_id,
                    "assistant",
                    output,
                    importance=0.5,
                )
                self.state = JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
                self.phase_runtime.voice_speaking()
                self._avatar_state("speaking", output)
                return output

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
            budget_seconds = self._execution_budget_seconds(trace.model_role, plan.agent)
            deadline = time.monotonic() + budget_seconds
            self._active_cancel_token = CancellationToken()
            self.runtime_context = {
                "state": "thinking",
                "task_id": trace.trace_id[:12],
                "task": text,
                "agent": plan.agent,
                "provider": "",
                "model_role": trace.model_role,
                "started_at": trace.started_at,
                "budget_seconds": budget_seconds,
                "deadline_monotonic": deadline,
                "last_event": "dispatch_started",
                "cancel_token": self._active_cancel_token,
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
                "execution_budget_seconds": budget_seconds,
                "cancel_token": self._active_cancel_token,
                "deadline_monotonic": deadline,
                "capabilities": self.capabilities.list(),
                "skills": [item for item in self.skills.list() if item.get("enabled")],
                "history": self.session.recent(24),
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
            self._avatar_activity("thinking", "")
            if hasattr(self.tool_broker, "set_task_context"):
                self.tool_broker.set_task_context(
                    agent=plan.agent,
                    task=text,
                )
            try:
                result = self.self_healing.run(
                    "agent_dispatch",
                    lambda: self.router.dispatch(text, metadata=dispatch_metadata),

                    metadata={
                        "approval_required": False,
                        "security_action": plan.agent in {"kali", "cybersecurity", "bugbounty"},
                    },
                )
            finally:
                if hasattr(self.tool_broker, "clear_task_context"):
                    self.tool_broker.clear_task_context()
            trace.metadata["self_healing"] = {
                "retries": self.self_healing.health.retries,
                "consecutive_failures": self.self_healing.health.consecutive_failures,
            }
            trace.actual_agent = result.agent
            self.task_lifecycle.transition(
                trace.trace_id,
                "running",
                provider=str(result.metadata.get("provider", "")),
            )
            self.runtime_context.update({
                "state": "result",
                "agent": result.agent,
                "provider": str(result.metadata.get("provider", "")),
                "last_event": "agent_result",
            })
            self._avatar_activity("thinking", "")
            trace.provider = str(result.metadata.get("provider", ""))
            for pending in result.metadata.get("pending_tools", []) or []:
                trace.add_tool_call(
                    name=str(pending.get("tool", "unknown")),
                    status="approval_required",
                    approval_required=True,
                )
            output = self.verifier.verify(text, result.content)
            from jenefar.voice.speech import devanagari_to_roman
            output = devanagari_to_roman(output)
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
                self.task_lifecycle.transition(trace.trace_id, "waiting_approval", reason="approval_required", provider=trace.provider)
                self.runtime_context.update({"state": "waiting_approval", "last_event": "approval_required"})
                self._register_pending_workflow(text, result, response_language=response_language)
                self.state = JenefarState.WAITING_APPROVAL
                self._avatar_state("waiting_approval", output)
            else:
                self.task_lifecycle.transition(trace.trace_id, "completed", provider=trace.provider)
                self.runtime_context.update({"state": "speaking", "last_event": "response_ready"})
                self.state = JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
                self._avatar_state("speaking", output)
            if not awaiting:
                self._active_cancel_token = None
                self.production.remember(output, kind="episodic", importance=0.5, provenance="assistant")
                self.production.task_finished(trace.trace_id, state="completed", agent=trace.actual_agent or result.agent, provider=trace.provider)
            return output
        except Exception as exc:
            cancelled = bool(self._active_cancel_token and self._active_cancel_token.cancelled)
            self.runtime_context.update({"state": "cancelled" if cancelled else "error", "last_event": str(exc)})
            trace.add_error(f"{type(exc).__name__}: {exc}")
            trace.finish(status="cancelled" if cancelled else "error", provider="cancelled" if cancelled else "error", verification={"passed": False})
            self.task_lifecycle.transition(
                trace.trace_id,
                "cancelled" if cancelled else "failed",
                reason=str(exc),
                provider="cancelled" if cancelled else "error",
            )
            self.trace_store.append(trace)
            self.production.task_finished(trace.trace_id, state="cancelled" if cancelled else "failed", agent=trace.actual_agent or trace.planned_agent, provider="cancelled" if cancelled else "error", error=str(exc))
            self.evaluator.evaluate(text, str(exc), provider="error", trace=trace.as_dict())
            self.state = JenefarState.SLEEPING
            self._avatar_state("cancelled" if cancelled else "error", str(exc))
            self._active_cancel_token = None
            if cancelled:
                return "Task cancel kar diya gaya hai."
            return f"Jenefar runtime error: {type(exc).__name__}: {exc}"

    @staticmethod
    def _confirmation_choice(text: str) -> str | None:
        lowered = " ".join(str(text or "").lower().strip().split())
        lowered = lowered.replace("?", "").replace("!", "").replace(".", "")
        negative = (
            "nahi", "nahin", "no", "cancel", "mat karo", "rehne do",
            "chod do", "chhod do", "don't", "do not", "stop"
        )
        positive = (
            "haan", "ha", "yes", "ok", "okay", "theek hai", "thik hai",
            "kar do", "proceed", "bhej do", "send kar do", "allow", "approve"
        )
        if any(item == lowered or lowered.startswith(item + " ") for item in negative):
            return "no"
        if any(item == lowered or lowered.startswith(item + " ") for item in positive):
            return "yes"
        return None

    def _handle_conversational_confirmation(
        self,
        text: str,
        *,
        response_language: str = "Hinglish",
    ) -> str | None:
        if not self.pending_approval_workflows:
            return None
        choice = self._confirmation_choice(text)
        if choice is None:
            return None

        pending_id = next(reversed(self.pending_approval_workflows))
        workflow = self.pending_approval_workflows.get(pending_id)
        if workflow is None:
            return None

        if choice == "no":
            raw = self._reject_pending_workflow(pending_id)
            from jenefar.voice.speech import devanagari_to_roman
            return devanagari_to_roman(raw)

        raw = self._approve_pending(pending_id)
        from jenefar.voice.speech import devanagari_to_roman
        return devanagari_to_roman(raw)

    def _reject_pending_workflow(self, pending_id: str) -> str:
        workflow = self.pending_approval_workflows.get(pending_id)
        result = self.tool_broker.reject(pending_id)
        if workflow is not None:
            for other_id in list(workflow.get("remaining") or set()):
                if other_id == pending_id:
                    continue
                self.tool_broker.reject(str(other_id))
                self.pending_approval_workflows.pop(str(other_id), None)
            workflow["remaining"] = set()
            self.pending_approval_workflows.pop(pending_id, None)
        task_id = str(workflow.get("task_id") or "")
        if task_id:
            self.task_lifecycle.transition(task_id, "completed", reason="approval_rejected")
            self.production.task_finished(task_id, state="completed", agent=str(workflow.get("agent") or ""), provider="approval", error="approval rejected")
        self.runtime_context.update({"state": "speaking", "last_event": "approval_rejected"})
        self._active_cancel_token = None
        self.state = JenefarState.SLEEPING
        return "Theek hai, ye action nahi karungi."

    @staticmethod
    def _is_explicit_screen_read_request(text: str) -> bool:
        lowered = " ".join(str(text or "").lower().split())
        markers = (
            "screen par kya", "screen pe kya", "screen me kya",
            "meri screen", "mere screen", "my screen", "read my screen",
            "screen dekho", "screen dikh", "screen read",
            "live screen", "what is on my screen", "what's on my screen",
        )
        return any(marker in lowered for marker in markers)

    def _direct_screen_read(self, text: str) -> str | None:
        if not self._is_explicit_screen_read_request(text):
            return None
        self.tool_broker.set_task_context(agent="gui_vision", task=text)
        try:
            raw = self.tool_broker.invoke("desktop_observe", {"query": text})
        finally:
            self.tool_broker.clear_task_context()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("status") != "ok":
            error = str(payload.get("error") or "").strip()
            if error:
                return "Meri local vision service abhi screen analysis nahi de pa rahi hai. " + error
            return None
        result = payload.get("result") or {}
        summary = str(result.get("summary") or "").strip()
        if summary:
            return summary
        elements = result.get("elements") or []
        labels = []
        for item in elements[:8]:
            label = str(item.get("label") or item.get("text") or "").strip()
            role = str(item.get("role") or "").strip()
            if label and label not in labels:
                labels.append(label + (f" ({role})" if role else ""))
        if labels:
            return "Screen par ye main items dikh rahe hain: " + ", ".join(labels[:6]) + "."
        return "Maine live screen capture kar li hai, lekin visible content ka reliable summary nahi mila."

    @staticmethod
    def _is_window_transfer_request(text: str) -> bool:
        lowered = " ".join(str(text or "").lower().split())
        markers = (
            "blue screen par", "blue screen pe", "holographic screen",
            "window transfer", "transfer window", "move window",
            "shift window", "window ko shift", "terminal ko blue",
            "firefox ko blue", "browser ko blue", "document folder ko blue",
            "terminal ko screen", "firefox ko screen", "browser ko screen",
        )
        return any(marker in lowered for marker in markers)

    def _direct_window_transfer(self, text: str) -> str | None:
        if not self._is_window_transfer_request(text):
            return None
        lowered = text.lower()
        candidates = (
            ("firefox", "Firefox"),
            ("chrome", "Chrome"),
            ("chromium", "Chromium"),
            ("terminal", "Terminal"),
            ("documents", "Documents"),
            ("file manager", "File Manager"),
            ("nautilus", "Nautilus"),
        )
        target = next((label for token, label in candidates if token in lowered), "")
        if not target:
            return None
        result = self.tool_broker.invoke(
            "desktop_window_transfer",
            {"query": target, "hide_native": True},
        )
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("status") != "ok":
            return None
        data = payload.get("result") or {}
        if data.get("native_hidden"):
            return f"{target} ab Jenefar ke blue screen par live dikh raha hai."
        return (
            f"{target} ka live mirror blue screen par chala diya hai. "
            "Native window ko hide karna current desktop backend me available nahi tha."
        )

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
        if text:
            print(f"[JENEFAR][ACTIVITY] {state.upper()}: {text}")
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
            "task_id": str(self.runtime_context.get("task_id") or ""),
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
            "deadline_monotonic": self.runtime_context.get("deadline_monotonic"),
            "cancel_token": self._active_cancel_token,
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
            task_id = str(workflow.get("task_id") or "")
            if task_id:
                self.task_lifecycle.transition(task_id, "completed", reason="approval_action_completed")
                self.production.task_finished(task_id, state="completed", agent=str(workflow.get("agent") or ""), provider="approval")
            self.runtime_context.update({"state": "speaking", "last_event": "approval_action_completed"})
            self._active_cancel_token = None
            self.state = JenefarState.SLEEPING
            return raw_result

        continue_kwargs = {
            "continue_tools": bool(getattr(agent, "use_tools", False)),
            "task_plan_text": str(workflow.get("task_plan_text") or ""),
            "deadline": workflow.get("deadline_monotonic"),
            "cancel_token": workflow.get("cancel_token"),
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
        if hasattr(self.tool_broker, "set_task_context"):
            self.tool_broker.set_task_context(
                agent=str(workflow.get("agent") or ""),
                task=str(workflow.get("task") or ""),
            )
        try:
            final_result = agent.continue_after_tools(
                workflow["task"],
                workflow["results"],
                **filtered_kwargs,
            )
        finally:
            if hasattr(self.tool_broker, "clear_task_context"):
                self.tool_broker.clear_task_context()
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
        task_id = str(workflow.get("task_id") or "")
        if task_id:
            provider = str(final_result.metadata.get("provider", ""))
            self.task_lifecycle.transition(task_id, "completed", provider=provider)
            self.production.task_finished(task_id, state="completed", agent=str(workflow.get("agent") or ""), provider=provider)
        self.runtime_context.update({"state": "speaking", "last_event": "approval_continuation_complete"})
        self._active_cancel_token = None
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
