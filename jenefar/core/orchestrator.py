from __future__ import annotations

import hashlib
import inspect
import ipaddress
import json
import os
import re
import threading
import time
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
from jenefar.core.production_runtime import ProductionRuntime
from jenefar.evaluation.runtime_status import build_runtime_snapshot
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
        # Approval callbacks can arrive through both voice and the dashboard.
        # Serialize them and reuse the first result so an action never executes twice.
        self._approval_lock = threading.RLock()
        self._approval_result_cache: dict[str, str] = {}
        self._latest_scan_result: dict | None = None
        self._latest_host_discovery: dict = {"target": "", "hosts": [], "own_ip": ""}
        self.offline_notice_open = False
        self.runtime_context: dict[str, Any] = {"state": "idle"}
        self._active_cancel_token: CancellationToken | None = None
        self._runtime_task_id: str | None = None
        self.task_lifecycle = TaskLifecycle()
        self.production = ProductionRuntime()

    def _ensure_runtime_components(self) -> None:
        """Lazily add runtime observability state for embedded/test instances."""
        if not hasattr(self, "task_lifecycle"):
            self.task_lifecycle = TaskLifecycle()
        if not hasattr(self, "runtime_context"):
            self.runtime_context = {"state": "idle"}
        if not hasattr(self, "_active_cancel_token"):
            self._active_cancel_token = None
        if not hasattr(self, "_runtime_task_id"):
            self._runtime_task_id = None
        # Keep legacy embedders and lightweight object.__new__ test fixtures
        # working without forcing persistent production stores into them.
        if not hasattr(self, "production"):
            self.production = None

    @staticmethod
    def _execution_budget_seconds(model_role: str, agent: str) -> float:
        role = str(model_role or "fast").strip().lower()
        agent_name = str(agent or "agent").strip().lower().replace("-", "_")
        agent_key = f"JENEFAR_AGENT_TIMEOUT_{agent_name.upper()}"
        role_key = f"JENEFAR_AGENT_TIMEOUT_{role.upper()}"
        raw = os.getenv(agent_key, os.getenv(role_key, os.getenv("JENEFAR_AGENT_TIMEOUT_SECONDS", "180")))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 180.0
        return min(max(value, 10.0), 300.0)

    @staticmethod
    def _late_dispatch_result_should_fail(deadline: float, result: Any, *, now: float | None = None) -> bool:
        """Reject late successes, but preserve a bounded provider-failure explanation.

        LLMClient may return an explicit offline_unavailable result after exhausting
        its bounded local retry. Raising another TimeoutError here discarded that
        useful response and made the chat show only 'execution budget exhausted'.
        """
        moment = time.monotonic() if now is None else float(now)
        if float(deadline) > moment:
            return False
        metadata = getattr(result, "metadata", {}) or {}
        provider = str(metadata.get("provider", "")).strip().lower()
        return provider not in {"offline_unavailable", "online_unavailable"}

    def cancel_active_task(self, reason: str = "cancelled by user") -> dict[str, Any]:
        token = self._active_cancel_token
        active = self.task_lifecycle.active()
        if token is None or token.cancelled or active is None:
            return {"cancelled": False, "active": False, "reason": "no cancellable active task"}
        changed = token.cancel(reason)
        if active.get("state") == "waiting_approval":
            # Reject all remaining approvals belonging to the single admitted
            # workflow before releasing the active-task slot.
            for pending_id in list(getattr(self, "pending_approval_workflows", {})):
                try:
                    self.tool_broker.reject(str(pending_id))
                except Exception:
                    pass
            getattr(self, "pending_approval_workflows", {}).clear()
            self._finish_waiting_runtime_task(state="cancelled", reason=token.reason, provider="user_cancel")
            self.runtime_context.update({"state": "cancelled", "last_event": token.reason})
        else:
            if active.get("state") != "cancelling":
                self.task_lifecycle.transition(active["task_id"], "cancelling", reason=token.reason)
            self.runtime_context.update({"state": "cancelling", "last_event": token.reason})
        return {"cancelled": changed, "active": True, "task_id": active["task_id"], "reason": token.reason}

    def runtime_status(self) -> dict[str, Any]:
        """Return a credential-safe live runtime snapshot for the operations UI."""
        from jenefar.core.provider_pool import ProviderPool
        provider_pool = ProviderPool()
        # Each agent owns an LLM client; combine their bounded in-process latency
        # windows so the dashboard reports real samples instead of a fresh empty pool.
        for agent in getattr(getattr(self, "router", None), "agents", []):
            client = getattr(agent, "llm", None)
            source_pool = getattr(client, "providers", None)
            if source_pool is None:
                continue
            for name in provider_pool.CONFIGS:
                samples = list(getattr(source_pool, "latency_samples", {}).get(name, []))
                if samples:
                    provider_pool.latency_samples[name] = (provider_pool.latency_samples[name] + samples)[-8:]
                provider_pool.failure_samples[name] += int(getattr(source_pool, "failure_samples", {}).get(name, 0))
        snapshot = build_runtime_snapshot(
            runtime_context=self.runtime_context,
            self_healing=self.self_healing,
            trace_store=self.trace_store,
            provider_pool=provider_pool,
        )
        snapshot["tasks"] = self.task_lifecycle.snapshot()
        snapshot["production"] = self.production.snapshot() if self.production is not None else {}
        return snapshot

    def runtime_tasks(
        self, *, search: str = "", state: str = "", agent: str = "",
        provider: str = "", limit: int = 20,
    ) -> dict[str, Any]:
        """Return filtered persistent task history for the runtime console."""
        return self.task_lifecycle.query_history(
            search=search, state=state, agent=agent, provider=provider, limit=limit,
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
        self._ensure_runtime_components()
        # Jenefar's user-facing runtime is intentionally Roman Hinglish-first.
        # Keep the language stable even when a caller omits the preference.
        response_language = response_language or "Hinglish"
        # Structured scan results belong to the current user request only.
        # Keep the previous host-discovery list separately for explicit follow-ups.
        self._latest_scan_result = None
        trace = ExecutionTrace(
            session_id=self.session.session_id,
            task=text,
            source=source,
            event_id=event_id,
        )

        def record_shortcut_trace(
            output: str,
            *,
            intent: str,
            provider: str = "local_runtime",
            status: str | None = None,
        ) -> None:
            trace.intent = intent
            trace.planned_agent = trace.planned_agent or "local_runtime"
            trace.actual_agent = trace.actual_agent or "local_runtime"
            trace.metadata["route"] = "direct_runtime"
            is_error = str(output).startswith("Jenefar runtime error:")
            final_status = status or ("error" if is_error else "success")
            trace.finish(
                status=final_status,
                provider=provider,
                verification={
                    "passed": bool(str(output).strip()) and not is_error,
                    "kind": "direct_runtime_response",
                },
            )
            self._persist_runtime_trace(
                trace,
                task=text,
                result=str(output),
                provider=provider,
            )
            if self._runtime_task_id == trace.trace_id:
                task_state = "waiting_approval" if final_status == "awaiting_approval" else ("failed" if final_status == "error" else "completed")
                try:
                    self.task_lifecycle.transition(trace.trace_id, task_state, reason=str(output) if task_state == "failed" else "", provider=provider, agent=trace.actual_agent or intent)
                    self.runtime_context.update({"state": task_state, "task_id": trace.trace_id[:12], "agent": trace.actual_agent or intent, "provider": provider, "last_event": intent})
                    if self.production is not None:
                        self.production.task_finished(trace.trace_id, state=task_state, agent=trace.actual_agent or intent, provider=provider, error=str(output) if task_state == "failed" else "")
                    if task_state != "waiting_approval":
                        self._runtime_task_id = None
                        self._active_cancel_token = None
                except (KeyError, ValueError, RuntimeError):
                    pass

        pending_reply = self._handle_conversational_confirmation(
            text,
            response_language=response_language,
        )
        if pending_reply is not None:
            # A scan-result window owns this response; don't also publish a
            # speaking transcript that would duplicate the host list in the HUD.
            if not getattr(self, "_latest_scan_result", None):
                self._avatar_state("speaking", pending_reply)
            record_shortcut_trace(
                pending_reply,
                intent="approval_confirmation",
                provider="local_confirmation",
                status="awaiting_approval" if self.state == JenefarState.WAITING_APPROVAL else None,
            )
            active = self.task_lifecycle.active()
            if active and active.get("state") == "waiting_approval" and self.state != JenefarState.WAITING_APPROVAL:
                try:
                    final_state = "cancelled" if any(word in pending_reply.casefold() for word in ("cancel", "reject", "decline", "mana kar")) else "completed"
                    self.task_lifecycle.transition(active["task_id"], final_state, reason=pending_reply, provider="local_confirmation")
                    if self.production is not None:
                        self.production.task_finished(active["task_id"], state=final_state, agent=active.get("agent", "approval"), provider="local_confirmation")
                    self.runtime_context.update({"state": final_state, "last_event": "approval_resolved"})
                    self._runtime_task_id = None
                    self._active_cancel_token = None
                except (KeyError, ValueError, RuntimeError):
                    pass
            return pending_reply
        if self.task_lifecycle.admit(trace.trace_id, text, agent="pending") is None:
            return "Jenefar abhi ek task execute kar rahi hai. Pehle current task complete ya cancel hone dein."
        self._runtime_task_id = trace.trace_id
        self.task_lifecycle.transition(trace.trace_id, "running")
        if self.production is not None:
            self.production.task_started(trace.trace_id, text, agent="pending")
        self.runtime_context = {"state": "thinking", "task_id": trace.trace_id[:12], "task": text, "agent": "pending", "provider": "", "started_at": time.time(), "last_event": "request_started"}
        self.state = JenefarState.THINKING
        self._avatar_state("thinking", "")
        self.session.add("user", text)
        self.memory_engine.record_message(
            self.session.session_id,
            "user",
            text,
            importance=0.55 if source == "user" else 0.5,
        )
        self.graph.learn_text(text)
        try:
            if self._is_local_host_port_scan_request(text):
                output = self._request_discovered_host_port_scan(text)
                self.session.add("assistant", output)
                self.memory_engine.record_message(
                    self.session.session_id,
                    "assistant",
                    output,
                    importance=0.6,
                )
                if self.state != JenefarState.WAITING_APPROVAL:
                    self.state = (
                        JenefarState.SLEEPING
                        if self.config.single_turn_sleep
                        else JenefarState.AWAKE
                    )
                if not self._latest_scan_result:
                    self._avatar_state("speaking", output)
                record_shortcut_trace(
                    output,
                    intent="network_port_scan",
                    provider="local_network",
                    status="awaiting_approval" if self.state == JenefarState.WAITING_APPROVAL else None,
                )
                return output

            if self._is_local_host_discovery_request(text):
                output = self._request_local_host_discovery(text)
                self.session.add("assistant", output)
                self.memory_engine.record_message(
                    self.session.session_id,
                    "assistant",
                    output,
                    importance=0.55,
                )
                awaiting = self.state == JenefarState.WAITING_APPROVAL
                if not awaiting:
                    self.state = (
                        JenefarState.SLEEPING
                        if self.config.single_turn_sleep
                        else JenefarState.AWAKE
                    )
                if self._latest_scan_result:
                    # BrowserVoiceBridge publishes the structured result event.
                    # Don't broadcast the same host list as a speech/chat event.
                    pass
                else:
                    self._avatar_state("waiting_approval" if awaiting else "speaking", output)
                record_shortcut_trace(
                    output,
                    intent="network_host_discovery",
                    provider="local_network",
                    status="awaiting_approval" if awaiting else None,
                )
                return output

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
                record_shortcut_trace(output, intent="window_transfer", provider="desktop")
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
                self._avatar_state("speaking", output)
                record_shortcut_trace(output, intent="screen_read", provider="desktop")
                return output

            if self._is_ip_info_query(text):
                output = self._local_ip_info_response()
                self.session.add("assistant", output)
                self.memory_engine.record_message(
                    self.session.session_id,
                    "assistant",
                    output,
                    importance=0.45,
                )
                self.state = JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
                self._avatar_state("speaking", output)
                record_shortcut_trace(output, intent="local_ip_info", provider="local_network")
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
                record_shortcut_trace(output, intent="local_time", provider="local_runtime")
                return output

            recall = self.memory_engine.recall(text, limit=8)
            graph_hits = self.graph.search(text.split()[0] if text.split() else text, limit=8)
            plan = self.planner.plan(text)
            task_plan = self.planner.task_planner.build(text, plan.intent, plan.agent)
            trace.intent = plan.intent
            trace.planned_agent = plan.agent
            trace.planner_confidence = plan.confidence
            trace.model_role = self._model_role_for_plan(plan)
            budget_seconds = self._execution_budget_seconds(trace.model_role, plan.agent)
            deadline = time.monotonic() + budget_seconds
            self._active_cancel_token = CancellationToken()
            self.runtime_context.update({
                "state": "thinking", "task_id": trace.trace_id[:12], "task": text,
                "agent": plan.agent, "provider": "", "model_role": trace.model_role,
                "started_at": time.time(), "budget_seconds": budget_seconds,
                "deadline_monotonic": deadline, "last_event": "dispatch_started",
            })
            self.task_lifecycle.transition(trace.trace_id, "running", agent=plan.agent)
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
                "execution_budget_seconds": budget_seconds,
                "deadline_monotonic": deadline,
                "cancel_token": self._active_cancel_token,
                "response_language": response_language,
                "source": source,
                "event_id": event_id,
                "runtime": runtime,
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
            retry_count_before = self.self_healing.health.retries
            task_actions: list[dict[str, str]] = []
            task_action_failures: list[dict[str, str]] = []
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
                        # Only the read-oriented research specialist is eligible for
                        # an automatic agent-dispatch retry. Other agents may perform
                        # writes, desktop actions, or other state-changing operations.
                        "retry_safe": plan.agent == "research",
                    },
                )
            finally:
                if hasattr(self.tool_broker, "consume_task_actions"):
                    task_actions = self.tool_broker.consume_task_actions()
                if hasattr(self.tool_broker, "consume_task_failures"):
                    task_action_failures = self.tool_broker.consume_task_failures()
                if hasattr(self.tool_broker, "clear_task_context"):
                    self.tool_broker.clear_task_context()
            trace.metadata["self_healing"] = {
                "retries": self.self_healing.health.retries - retry_count_before,
                "total_retries": self.self_healing.health.retries,
                "consecutive_failures": self.self_healing.health.consecutive_failures,
            }
            if self._active_cancel_token is not None:
                self._active_cancel_token.raise_if_cancelled()
            if self._late_dispatch_result_should_fail(deadline, result):
                raise TimeoutError("Jenefar execution budget exhausted")
            trace.actual_agent = result.agent
            result_provider = str(result.metadata.get("provider", ""))
            provider_unavailable = result_provider in {"offline_unavailable", "online_unavailable"}
            self.runtime_context.update({
                "agent": result.agent,
                "provider": result_provider,
                "last_event": "provider_unavailable" if provider_unavailable else "agent_result",
            })
            successful_tool_names = {
                str(action.get("tool") or "unknown")
                for action in task_actions
            }
            unresolved_tool_failures = [
                failure for failure in task_action_failures
                if str(failure.get("tool") or "unknown") not in successful_tool_names
            ]
            trace.metadata["tool_failures"] = task_action_failures[:20]
            for action in task_actions:
                trace.add_tool_call(
                    name=str(action.get("tool") or "unknown"),
                    status="success",
                )
            for failure in task_action_failures[:20]:
                trace.add_tool_call(
                    name=str(failure.get("tool") or "unknown"),
                    status="failed",
                    result={
                        "stage": str(failure.get("stage") or "execution")[:60],
                        "error": str(failure.get("error") or "Tool failed")[:500],
                    },
                )
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
            if unresolved_tool_failures:
                failures_text = "; ".join(
                    f"{str(item.get('tool') or 'unknown')} "
                    f"[{str(item.get('stage') or 'execution')}]: "
                    f"{str(item.get('error') or 'tool failed')[:250]}"
                    for item in unresolved_tool_failures[:5]
                )
                trace.add_error(
                    "Tool execution was not verified as successful: " + failures_text
                )
                original_output = str(output or "").strip()
                output = (
                    "Task ko successfully complete verify nahi kar saka. "
                    "Yeh tool attempt fail hua, isliye main action ko successful mark nahi kar raha: "
                    + failures_text
                    + (
                        "\nAssistant ka unverified summary: " + original_output[:600]
                        if original_output else ""
                    )
                )
            verification = {
                "passed": bool(output and output.strip())
                and not provider_unavailable
                and not unresolved_tool_failures,
                "verifier": self.verifier.__class__.__name__,
                "provider_available": not provider_unavailable,
                "unresolved_tool_failures": unresolved_tool_failures[:5],
            }
            awaiting = result.metadata.get("provider") in {"approval_required", "local_approval_required"}
            has_execution_failure = bool(unresolved_tool_failures)
            task_failed = provider_unavailable or has_execution_failure
            trace.finish(
                status="awaiting_approval" if awaiting else ("error" if task_failed else "success"),
                provider=trace.provider,
                verification=verification,
            )
            if not awaiting and verification["passed"]:
                self._auto_learn_successful_workflow(text, plan.agent, task_actions)
            self.session.add("assistant", output)
            if not provider_unavailable:
                self.memory_engine.record_message(
                    self.session.session_id,
                    "assistant",
                    output,
                    importance=0.5,
                )
                if not has_execution_failure:
                    self.graph.learn_text(output)
                    if len(self.session.messages) % 6 == 0:
                        self.memory_engine.consolidate_messages(
                            self.session.session_id,
                            self.session.recent(12),
                            importance=0.72,
                        )
            self._persist_runtime_trace(
                trace,
                task=text,
                result=output,
                provider=trace.provider,
            )
            if awaiting:
                self._register_pending_workflow(text, result, response_language=response_language)
                self.state = JenefarState.WAITING_APPROVAL
                self._avatar_state("waiting_approval", output)
            else:
                self.state = JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
                self._avatar_state("error" if task_failed else "speaking", output)
            if awaiting:
                self.task_lifecycle.transition(trace.trace_id, "waiting_approval", reason="approval_required", provider=trace.provider, agent=trace.actual_agent or trace.planned_agent)
                self.runtime_context.update({"state": "waiting_approval", "last_event": "approval_required"})
                if self.production is not None:
                    self.production.task_finished(trace.trace_id, state="waiting_approval", agent=trace.actual_agent or trace.planned_agent, provider=trace.provider)
            else:
                final_task_state = "failed" if task_failed else "completed"
                failure_reason = output if task_failed else ""
                self.task_lifecycle.transition(
                    trace.trace_id,
                    final_task_state,
                    reason=failure_reason,
                    provider=trace.provider,
                    agent=trace.actual_agent or trace.planned_agent,
                )
                self.runtime_context.update({
                    "state": "error" if task_failed else "speaking",
                    "last_event": (
                        "tool_execution_failed" if has_execution_failure
                        else "provider_unavailable" if provider_unavailable
                        else "response_ready"
                    ),
                })
                if self.production is not None:
                    if not task_failed:
                        self.production.remember(output, kind="episodic", importance=0.5, provenance="assistant")
                    self.production.task_finished(
                        trace.trace_id,
                        state=final_task_state,
                        agent=trace.actual_agent or trace.planned_agent,
                        provider=trace.provider,
                        error=failure_reason,
                    )
                self._runtime_task_id = None
                self._active_cancel_token = None
            return output
        except Exception as exc:
            cancelled = bool(self._active_cancel_token and self._active_cancel_token.cancelled)
            self.runtime_context.update({"state": "cancelled" if cancelled else "error", "last_event": str(exc)})
            trace.add_error(f"{type(exc).__name__}: {exc}")
            healing = getattr(self, "self_healing", None)
            if healing is not None:
                trace.metadata["self_healing"] = {
                    "retries": max(0, healing.health.retries - locals().get("retry_count_before", healing.health.retries)),
                    "total_retries": healing.health.retries,
                    "consecutive_failures": healing.health.consecutive_failures,
                    "circuit_open": healing.health.circuit_open,
                }
            trace.finish(status="cancelled" if cancelled else "error", provider="cancelled" if cancelled else "error", verification={"passed": False})
            self._persist_runtime_trace(
                trace,
                task=text,
                result=str(exc),
                provider="cancelled" if cancelled else "error",
            )
            try:
                self.task_lifecycle.transition(trace.trace_id, "cancelled" if cancelled else "failed", reason=str(exc), provider="cancelled" if cancelled else "error")
                if self.production is not None:
                    self.production.task_finished(trace.trace_id, state="cancelled" if cancelled else "failed", agent=trace.actual_agent or trace.planned_agent, provider="cancelled" if cancelled else "error", error=str(exc))
            except (KeyError, ValueError, RuntimeError):
                pass
            self._runtime_task_id = None
            self._active_cancel_token = None
            self.state = JenefarState.SLEEPING
            self._avatar_state("cancelled" if cancelled else "error", str(exc))
            return "Task cancel kar diya gaya hai." if cancelled else f"Jenefar runtime error: {type(exc).__name__}: {exc}"

    def _persist_runtime_trace(
        self,
        trace: ExecutionTrace,
        *,
        task: str,
        result: str,
        provider: str,
    ) -> None:
        """Persist diagnostics best-effort so logging failures never fail user work."""
        try:
            self.evaluator.evaluate(
                task,
                result,
                provider=provider,
                trace=trace.as_dict(),
            )
        except Exception as exc:
            trace.metadata.setdefault("diagnostic_errors", []).append(
                f"evaluation persistence failed: {type(exc).__name__}"
            )
        try:
            self.trace_store.append(trace)
        except Exception as exc:
            # Do not let an unavailable local disk or a malformed diagnostics path
            # turn an otherwise completed task into a user-visible runtime failure.
            trace.metadata.setdefault("diagnostic_errors", []).append(
                f"trace persistence failed: {type(exc).__name__}"
            )
            print(f"[JENEFAR] Runtime trace persistence warning: {type(exc).__name__}")

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

    def _finish_waiting_runtime_task(self, *, state: str, reason: str, provider: str = "approval") -> None:
        """Finalize a lifecycle task after its last approval is resolved."""
        lifecycle = getattr(self, "task_lifecycle", None)
        record = lifecycle.active() if lifecycle is not None else None
        if not record or record.get("state") != "waiting_approval":
            return
        task_id = str(record.get("task_id") or "")
        try:
            lifecycle.transition(task_id, state, reason=reason, provider=provider)
            production = getattr(self, "production", None)
            if production is not None:
                production.task_finished(task_id, state=state, agent=str(record.get("agent") or "approval"), provider=provider, error=reason if state in {"failed", "cancelled"} else "")
            context = getattr(self, "runtime_context", None)
            if isinstance(context, dict):
                context.update({"state": state, "last_event": "approval_resolved"})
            self._runtime_task_id = None
            self._active_cancel_token = None
        except (KeyError, ValueError, RuntimeError):
            # Approval resolution must not hide the actual tool result.
            return

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
        self.state = JenefarState.SLEEPING
        self._finish_waiting_runtime_task(state="cancelled", reason="User rejected pending tool action")
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
    def _is_local_host_discovery_request(text: str) -> bool:
        """Recognize explicit requests to count live hosts in a selected network."""
        lowered = " ".join(str(text or "").casefold().split())
        if not lowered:
            return False

        cidr = bool(re.search(
            r"(?<![0-9.])(?:[0-9]{1,3}[.]){3}[0-9]{1,3}/[0-9]{1,2}(?![0-9.])",
            lowered,
        ))
        has_range = any(marker in lowered for marker in (
            "ip range", "ip ki range", "range", "subnet", "cidr",
            "network range", "local network", "my subnet", "meri subnet",
            "meri range", "my range", "mere network", "mera network",
            "meri network", "apne network", "apna network", "apni network",
            "current network", "my lan", "meri lan", "apna lan",
        ))
        has_host_goal = any(marker in lowered for marker in (
            "host", "hosts", "device", "devices", "online", "live",
            "ping sweep", "host discovery", "kitne", "count", "discover",
            "scan",
        ))
        explicit_goal = any(marker in lowered for marker in (
            "host discovery", "live hosts", "online hosts", "hosts online",
            "kitne host", "kitne hosts", "kitne device", "kitne devices",
            "ping sweep", "check online host", "check live host",
            "scan my network", "scan the network", "scan local network",
            "scan network", "network scan", "check the network",
            "scan my lan", "scan local lan", "mere network ko scan",
            "mera network scan", "meri network scan", "apne network ko scan",
            "network ko scan", "network scan karke", "scan karke live host",
            "live host detect", "live hosts detect", "host ko detect",
            "hosts ko detect", "network ke live host", "network par live host",
        ))
        # Hinglish word order varies ("mere network ko scan karo", "network
        # scan karke live hosts dikhao"). Catch explicit current-network requests
        # before they can fall through to an LLM, without treating unrelated
        # mentions of networking as a request to execute a scan.
        has_network_reference = bool(re.search(
            r"\b(?:network|networks|lan|subnet|ip range|cidr)\b", lowered
        ))
        has_scan_verb = bool(re.search(
            r"\b(?:scan|scanning|check|detect|discover|find|show|list|identify)\b", lowered
        )) or any(phrase in lowered for phrase in ("pata karo", "pata lagao", "dikhao", "nikalo", "check karo", "scan karo"))
        has_live_host_goal = any(marker in lowered for marker in (
            "live host", "live hosts", "online host", "online hosts",
            "host online", "hosts online", "device online", "devices online",
            "host detect", "hosts detect", "host discovery", "kitne host",
            "kitne device", "live device", "live devices",
        ))
        current_network_reference = any(marker in lowered for marker in (
            "my network", "mere network", "mera network", "meri network",
            "apne network", "apna network", "apni network", "current network",
            "local network", "my lan", "meri lan", "apna lan",
        ))
        return (
            explicit_goal
            or (has_host_goal and (has_range or cidr))
            or (has_network_reference and has_scan_verb and has_live_host_goal)
            or (current_network_reference and has_scan_verb)
        )

    @staticmethod
    def _is_local_host_port_scan_request(text: str) -> bool:
        lowered = " ".join(str(text or "").casefold().split())
        if not lowered:
            return False
        markers = (
            "port scan", "scan ports", "scan port", "ports of", "port of",
            "ke ports", "ke port", "port ko scan", "open ports", "check ports",
            "ports scan", "port check", "porton ko scan",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _host_ordinal(text: str) -> int | None:
        lowered = " ".join(str(text or "").casefold().split())
        ordinal_patterns = (
            (r"\b(?:first|1st|pehla|pahla|pehli|pahli)\b", 1),
            (r"\b(?:second|2nd|doosra|dusra|doosri|dusri)\b", 2),
            (r"\b(?:third|3rd|teesra|tisra|teesri|tisri)\b", 3),
            (r"\b(?:fourth|4th|chautha|chauthi)\b", 4),
            (r"\b(?:fifth|5th|paanchva|panchva|panchvi)\b", 5),
        )
        for pattern, index in ordinal_patterns:
            if re.search(pattern, lowered):
                return index
        numbered_target = re.search(
            r"\b(?:target|host|device|machine)\s*(?:number|no\.?|#)?\s*(\d{1,2})\b",
            lowered,
        )
        if numbered_target:
            return int(numbered_target.group(1))
        number_before_target = re.search(
            r"\b(?:number|no\.?|#)\s*(\d{1,2})\s+(?:target|host|device|machine)\b",
            lowered,
        )
        if number_before_target:
            return int(number_before_target.group(1))
        numbered = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)\s+(?:host|device|machine|target)\b",
            lowered,
        )
        return int(numbered.group(1)) if numbered else None

    def _request_discovered_host_port_scan(self, text: str) -> str:
        """Run a bounded Nmap TCP service scan only against a recently discovered live host."""
        from datetime import datetime, timezone

        latest = getattr(self, "_latest_host_discovery", {}) or {}
        hosts = latest.get("hosts") if isinstance(latest, dict) else None
        if not isinstance(hosts, list) or not hosts:
            return "Pehle authorized local network par live-host discovery karo. Abhi koi saved live-host list nahi hai."

        ip_match = re.search(
            r"(?<![0-9.])((?:[0-9]{1,3}\.){3}[0-9]{1,3})(?![0-9.])",
            str(text or ""),
        )
        selected_ip = ""
        selected_index = 0
        if ip_match:
            try:
                selected_ip = str(ipaddress.IPv4Address(ip_match.group(1)))
            except ipaddress.AddressValueError:
                return "Diya gaya IPv4 address valid nahi hai; port scan execute nahi hua."
            for index, host in enumerate(hosts, 1):
                if isinstance(host, dict) and str(host.get("ip") or "") == selected_ip:
                    selected_index = index
                    break
            if not selected_index:
                return "Ye IP latest live-host results mein nahi hai. Pehle host discovery dobara chalao ya displayed live host select karo."
        else:
            selected_index = self._host_ordinal(text) or 0
            if not selected_index:
                return "Kis live host ke ports scan karne hain? Latest Scan Results window se host select karo ya bolo: 'second host ke ports scan karo'."
            if selected_index < 1 or selected_index > len(hosts):
                return f"Latest scan mein sirf {len(hosts)} live hosts mile the. Host number {selected_index} available nahi hai."
            chosen = hosts[selected_index - 1]
            selected_ip = str(chosen.get("ip") or "") if isinstance(chosen, dict) else ""
            try:
                selected_ip = str(ipaddress.IPv4Address(selected_ip))
            except ipaddress.AddressValueError:
                return "Selected host ke paas valid IPv4 address nahi hai; koi port scan execute nahi hua."

        plan = (
            "User explicitly requested a port scan of one host from Jenefar's most recent authorized local host-discovery results. "
            f"Selected live host #{selected_index}: {selected_ip}. Re-check JENEFAR_AUTHORIZED_TARGETS scope, then run only "
            "Nmap TCP connect scan with service identification over the top 1000 TCP ports, -Pn (skip ping discovery for the recently live host), -n, -T3, one retry, and a 120-second timeout. "
            "No subnet scan, UDP scan, vulnerability scripts, exploitation, or additional targets."
        )
        arguments = {
            "tool": "nmap",
            "args": [
                # This host was just reported live; skip Nmap's separate ping
                # discovery so ICMP-filtering devices still receive a port probe.
                "-Pn", "-n", "-sT", "-sV", "-T3", "--max-retries", "1",
                "--top-ports", "1000", selected_ip,
            ],
            "target": selected_ip,
            "timeout": 120,
            "plan": plan,
        }
        try:
            # This user's direct, explicit port-scan request is the confirmation.
            # ToolBroker still runs its normal executable, argument, and target-scope preflight.
            raw = self.tool_broker.invoke("kali_tool_execute", arguments, confirmed=True)
            payload = json.loads(raw)
        except Exception as exc:
            return f"{selected_ip} ka port scan start nahi ho paaya: {type(exc).__name__}: {exc}"

        if not isinstance(payload, dict) or payload.get("status") != "ok":
            error = str(payload.get("error") or "authorization/preflight failed") if isinstance(payload, dict) else "invalid tool response"
            return f"{selected_ip} ka port scan block hua: {error}. Authorization scope aur Nmap availability check karo."

        summary = f"{selected_ip} ka port scan complete."
        data = self._build_port_scan_result(
            raw,
            selected_ip,
            host_index=selected_index,
            previous_hosts=hosts,
            completed_at=datetime.now(timezone.utc).isoformat(),
            host_discovery_target=str(latest.get("target") or ""),
            own_ip=str(latest.get("own_ip") or ""),
        )
        if data is None:
            return summary + " Lekin verified port output parse nahi ho paaya."
        self._latest_scan_result = data
        avatar = getattr(self, "avatar", None)
        if avatar is not None:
            avatar.publish("scan_results", str(data["summary"]), data=data)
        return str(data["summary"])

    def _publish_network_scan_guidance(
        self,
        *,
        target: str,
        status: str,
        summary: str,
        reason: str = "",
        interface: str = "",
        local_address: str = "",
        networks: list[dict] | None = None,
    ) -> str:
        """Publish an actionable network-selection/scope result without implying a scan ran."""
        scope = getattr(self, "scope", None) or getattr(
            getattr(self, "tool_broker", None), "scope", None
        )
        allowed_targets = list(getattr(scope, "allowed_targets", []) or [])
        options: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in networks or []:
            if not isinstance(item, dict):
                continue
            network = str(item.get("network") or item.get("cidr") or "").strip()
            if not network:
                continue
            iface = str(item.get("interface") or "selected CIDR").strip()
            identity = (iface, network)
            if identity in seen:
                continue
            seen.add(identity)
            try:
                authorized = bool(scope and scope.allows(network))
            except Exception:
                authorized = False
            options.append({
                "interface": iface,
                "address": str(item.get("address") or ""),
                "network": network,
                "prefixlen": item.get("prefixlen"),
                "num_addresses": item.get("num_addresses"),
                "authorized": authorized,
            })

        if target and not any(item["network"] == target for item in options):
            try:
                authorized = bool(scope and scope.allows(target))
            except Exception:
                authorized = False
            options.insert(0, {
                "interface": interface or "selected CIDR",
                "address": str(local_address or ""),
                "network": str(target),
                "prefixlen": None,
                "num_addresses": None,
                "authorized": authorized,
            })

        # Never allow a stale successful discovery list to survive a blocked or
        # ambiguous scan request: later ordinal commands must not use old hosts.
        self._latest_host_discovery = {
            "target": str(target or ""),
            "hosts": [],
            "own_ip": str(local_address or ""),
        }
        data = {
            "kind": "host_discovery",
            "title": (
                "AUTHORIZATION REQUIRED" if status == "blocked"
                else "SELECT NETWORK" if status == "selection_required"
                else "SCAN FAILED"
            ),
            "scan_status": status,
            "target": str(target or ""),
            "interface": str(interface or ""),
            "own_ip": str(local_address or ""),
            "summary": str(summary),
            "scope_message": str(reason or ""),
            "authorized_targets": allowed_targets,
            "available_networks": options,
            "host_count": None,
            "address_count": None,
            "hosts": [],
            "command": "",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "completed_at": __import__("datetime").datetime.now().astimezone().isoformat(),
            "scan_type": "Nmap host discovery (-sn), not executed",
        }
        self._latest_scan_result = data
        avatar = getattr(self, "avatar", None)
        if avatar is not None and hasattr(avatar, "publish"):
            avatar.publish("scan_results", str(data["summary"]), data=data)
        return str(summary) + ((" " + str(reason)) if reason else "")

    def _request_local_host_discovery(self, text: str) -> str:
        """Plan a bounded host-only scan of a clearly selected, authorized IPv4 range."""
        import ipaddress

        explicit = re.search(
            r"(?<![0-9.])((?:[0-9]{1,3}[.]){3}[0-9]{1,3}/[0-9]{1,2})(?![0-9.])",
            str(text or ""),
        )
        interface = "user-specified CIDR"
        local_address = ""
        candidate_networks: list[dict] = []
        if explicit:
            try:
                network = ipaddress.ip_network(explicit.group(1), strict=False)
            except ValueError:
                return "Diya gaya CIDR valid nahi hai. Example: 192.168.29.0/24. Koi scan execute nahi hua."
            candidate_networks = [{
                "interface": interface,
                "address": "",
                "network": str(network),
                "prefixlen": network.prefixlen,
                "num_addresses": network.num_addresses,
            }]
        else:
            local_range_reference = any(marker in str(text or "").casefold() for marker in (
                "meri ip", "mera ip", "mere ip", "my ip",
                "my network", "mere network", "mera network", "meri network",
                "apne network", "apna network", "apni network", "current network",
                "local network", "my lan", "meri lan", "apna lan",
                "my subnet", "meri subnet", "meri range", "my range",
            ))
            if not local_range_reference:
                return (
                    "Host discovery ke liye exact IPv4 CIDR batao (example: 192.168.29.0/24), "
                    "ya clearly bolo ki current local IP range use karni hai. Abhi koi scan execute nahi hua."
                )
            from jenefar.tools.network_info import get_primary_private_ipv4_network

            selected = get_primary_private_ipv4_network()
            candidate_networks = list(selected.get("networks") or [])
            if selected.get("status") != "ok":
                candidates = candidate_networks or []
                if selected.get("status") == "ambiguous" and candidates:
                    return self._publish_network_scan_guidance(
                        target="",
                        status="selection_required",
                        summary="Multiple local IPv4 networks detected. Select an interface/network in the results window.",
                        reason=str(selected.get("error") or "Choose the intended active local interface. No scan has run."),
                        interface=str(selected.get("default_interface") or ""),
                        networks=candidates,
                    )
                detail = str(selected.get("error") or selected.get("status") or "unknown error")
                return self._publish_network_scan_guidance(
                    target="",
                    status="error",
                    summary="Local network selection failed. No Nmap command was executed.",
                    reason=detail,
                    networks=candidates,
                )
            if not candidate_networks:
                candidate_networks = [selected]
            try:
                network = ipaddress.ip_network(str(selected["network"]), strict=False)
            except (KeyError, ValueError):
                return "Local interface se valid CIDR nahi mila. Exact CIDR specify karo. Koi scan execute nahi hua."
            interface = str(selected.get("interface") or "active interface")
            local_address = str(selected.get("address") or "")

        if network.version != 4:
            return "Ye workflow filhaal IPv4 host discovery support karta hai. Koi scan execute nahi hua."
        if network.num_addresses > 4096:
            return (
                f"Selected range {network} mein {network.num_addresses} addresses hain, jo automatic discovery limit "
                "4096 se zyada hai. Isse chhote authorized CIDR mein divide karke do. Koi scan execute nahi hua."
            )
        target = str(network)
        if not any(str(item.get("network") or "") == target for item in candidate_networks if isinstance(item, dict)):
            candidate_networks.insert(0, {
                "interface": interface,
                "address": local_address,
                "network": target,
                "prefixlen": network.prefixlen,
                "num_addresses": network.num_addresses,
            })

        active_scope = getattr(self, "scope", None) or getattr(
            getattr(self, "tool_broker", None), "scope", None
        )
        if active_scope is not None and not active_scope.allows(target):
            explanation = active_scope.explain(target)
            return self._publish_network_scan_guidance(
                target=target,
                status="blocked",
                summary=f"Scan blocked before execution: {target} is outside the configured authorization scope. No Nmap command was executed.",
                reason=explanation,
                interface=interface,
                local_address=local_address,
                networks=candidate_networks,
            )

        plan_text = (
            "Goal: count hosts responding on the selected IPv4 network. "
            f"Selected target: {target} (interface: {interface}"
            + (f", local address: {local_address}" if local_address else "")
            + "). Plan: verify configured authorization scope; run Nmap host discovery only with "
            "-sn, numeric targets (-n), conservative timing (-T3), and one retry; report hosts up. "
            "This direct request authorizes only host discovery; do not enumerate ports or services. "
            "Configured target scope must still pass."
        )
        arguments = {
            "tool": "nmap",
            "args": [
                "-sn", "-n", "-T3", "--max-retries", "1", target,
            ],
            "target": target,
            "timeout": 90,
            "plan": plan_text,
        }
        try:
            # This direct, explicit request for the user's current LAN is confirmation
            # for bounded host discovery. The broker still enforces authorized target
            # scope, executable validation, and command preflight.
            raw = self.tool_broker.invoke("kali_tool_execute", arguments, confirmed=True)
            payload = json.loads(raw)
        except Exception as exc:
            return (
                f"Host-discovery plan target {target} ke liye ready tha, lekin preflight result read nahi hua: "
                f"{type(exc).__name__}: {exc}. Koi scan execute nahi hua."
            )

        if not isinstance(payload, dict):
            return f"Host discovery preflight ne invalid response diya for {target}. Koi scan execute nahi hua."
        if payload.get("status") == "approval_required":
            pending_id = str(payload.get("pending_id") or "").strip()
            user_prompt = str(payload.get("user_prompt") or "").strip()
            if not pending_id or not user_prompt:
                return f"Target {target} validate hua, lekin approval request incomplete thi. Koi scan execute nahi hua."
            workflow = {
                "task": text,
                "agent": "network_host_discovery",
                "response_language": "Hinglish",
                "task_plan_text": plan_text,
                "remaining": {pending_id},
                "results": [],
                "direct_workflow": "local_host_discovery",
                "target": target,
                "interface": interface,
                "local_address": local_address,
            }
            self.pending_approval_workflows[pending_id] = workflow
            self.state = JenefarState.WAITING_APPROVAL
            return (
                f"Task analysis complete. Selected range: {target} via {interface}. "
                "Execution se pehle approval zaroori hai.\n\n" + user_prompt
            )
        if payload.get("status") == "ok":
            summary = self._summarize_local_host_discovery(raw, target)
            result_data = self._record_host_discovery_result(
                raw, target, summary, local_address=local_address
            )
            if result_data is not None:
                active_scope = getattr(self, "scope", None) or getattr(
                    getattr(self, "tool_broker", None), "scope", None
                )
                result_data["interface"] = interface
                result_data["available_networks"] = [
                    {
                        "interface": str(item.get("interface") or "selected CIDR"),
                        "address": str(item.get("address") or ""),
                        "network": str(item.get("network") or ""),
                        "prefixlen": item.get("prefixlen"),
                        "num_addresses": item.get("num_addresses"),
                        "authorized": bool(active_scope and active_scope.allows(str(item.get("network") or ""))),
                    }
                    for item in candidate_networks
                    if isinstance(item, dict) and item.get("network")
                ]
                result_data["authorized_targets"] = list(getattr(active_scope, "allowed_targets", []) or [])
            avatar = getattr(self, "avatar", None)
            if result_data and avatar is not None:
                avatar.publish("scan_results", str(result_data["summary"]), data=result_data)
            return summary
        error = str(payload.get("error") or "authorization/tool preflight blocked execution")
        scope_blocked = "scope" in error.casefold() or "outside the configured authorization" in error.casefold()
        return self._publish_network_scan_guidance(
            target=target,
            status="blocked" if scope_blocked else "error",
            summary=(
                f"Scan blocked before execution for {target}; no Nmap command ran."
                if scope_blocked
                else f"Host discovery failed during preflight for {target}; no verified host count is available."
            ),
            reason=error,
            interface=interface,
            local_address=local_address,
            networks=candidate_networks,
        )

    @staticmethod
    def _summarize_local_host_discovery(raw_result: str, target: str) -> str:
        """Summarize actual Nmap host-discovery output, never inventing a host count."""
        try:
            payload = json.loads(raw_result)
        except (TypeError, json.JSONDecodeError):
            return f"{target} ke liye scan result parse nahi ho paaya. Raw execution output unavailable hai."

        if not isinstance(payload, dict) or payload.get("status") != "ok":
            error = (
                str(payload.get("error") or payload.get("message") or "tool execution failed")
                if isinstance(payload, dict) else "invalid tool response"
            )
            return f"{target} ka host discovery execute nahi ho paaya: {error}. Koi verified host count available nahi hai."

        result = payload.get("result")
        if not isinstance(result, dict):
            return f"{target} ka tool result invalid tha. Koi verified host count available nahi hai."
        return_code = result.get("returncode")
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        if return_code != 0:
            detail = (stderr or stdout or "no diagnostic output").strip()[-700:]
            return f"{target} par Nmap host discovery fail hua (exit code {return_code}): {detail}"

        done = re.search(
            r"Nmap done: *([0-9,]+) +IP address(?:es)? +[(]([0-9,]+) +hosts? up[)]",
            stdout,
            re.IGNORECASE,
        )
        reports = [
            line.split(" for ", 1)[1].strip()
            for line in stdout.splitlines()
            if line.strip().startswith("Nmap scan report for ")
        ]
        if done:
            address_count = int(done.group(1).replace(",", ""))
            host_count = int(done.group(2).replace(",", ""))
        elif reports:
            address_count = None
            host_count = len(reports)
        else:
            return (
                f"Nmap ne {target} ke liye successful exit diya, lekin standard host-count summary nahi mili. "
                "Main host count guess nahi karungi. Output: " + (stdout[-700:].strip() or "empty")
            )

        summary = (
            f"Host discovery complete: {host_count} host(s) online/response dete mile, "
            f"{address_count if address_count is not None else 'unknown'} addresses checked in {target}. "
            "Command Nmap -sn tha; ports aur services scan nahi kiye gaye."
        )
        # Keep the full diagnostic summary available to CLI/tests and logs.
        # BrowserVoiceBridge detects structured scan data separately and sends
        # only the compact result-window summary to the voice UI.
        if reports:
            summary += "\nReported hosts: " + ", ".join(reports[:30])
            if len(reports) > 30:
                summary += f" (aur {len(reports) - 30} hosts)"
        return summary

    @staticmethod
    def _nmap_payload(raw_result: str) -> dict | None:
        try:
            payload = json.loads(raw_result)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            return None
        result = payload.get("result")
        return result if isinstance(result, dict) else None

    def _record_host_discovery_result(
        self,
        raw_result: str,
        target: str,
        summary: str,
        *,
        local_address: str = "",
    ) -> dict | None:
        result = self._nmap_payload(raw_result)
        if not result:
            return None

        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        returncode = result.get("returncode")
        completed_at = __import__("datetime").datetime.now().astimezone().isoformat()
        if returncode != 0:
            failed = {
                "kind": "host_discovery",
                "title": "SCAN FAILED",
                "scan_status": "error",
                "target": str(target),
                "summary": f"Nmap host discovery failed (exit code {returncode})",
                "host_count": 0,
                "address_count": None,
                "hosts": [],
                "own_ip": str(local_address or ""),
                "command": str(result.get("command") or ""),
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
                "completed_at": completed_at,
                "scan_type": "Nmap host discovery (-sn)",
            }
            # Clear a previous live-host list after a failed fresh scan so a
            # subsequent ordinal request cannot silently reuse stale hosts.
            self._latest_host_discovery = {
                "target": str(target), "hosts": [], "own_ip": str(local_address or ""),
                "completed_at": completed_at,
            }
            self._latest_scan_result = failed
            return failed

        hosts: list[dict] = []
        current = None
        for line in stdout.splitlines():
            report = re.match(r"^Nmap scan report for (.+?)\s*$", line.strip(), re.IGNORECASE)
            if report:
                raw_ip = report.group(1).strip()
                try:
                    ip = str(ipaddress.IPv4Address(raw_ip))
                except ipaddress.AddressValueError:
                    current = None
                    continue
                current = {
                    "index": len(hosts) + 1,
                    "ip": ip,
                    "state": "UP",
                    "latency": "",
                    "mac": "",
                    "vendor": "",
                    "is_local": bool(local_address and ip == local_address),
                }
                hosts.append(current)
                continue
            if current is None:
                continue
            latency = re.search(r"Host is up \(([^)]+)\)", line.strip(), re.IGNORECASE)
            if latency:
                current["latency"] = latency.group(1).strip()
            mac = re.search(r"MAC Address:\s*([0-9a-f:.-]{17})(?:\s+\((.*?)\))?", line.strip(), re.IGNORECASE)
            if mac:
                current["mac"] = mac.group(1).upper()
                current["vendor"] = str(mac.group(2) or "").strip()

        count_match = re.search(
            r"Nmap done:\s*([0-9,]+)\s+IP addresses?\s+\(([0-9,]+)\s+hosts? up\)",
            stdout,
            re.IGNORECASE,
        )
        reported_count = int(count_match.group(1).replace(",", "")) if count_match else None
        host_count = len(hosts)
        parse_complete = bool(count_match or hosts)
        completed_at = __import__("datetime").datetime.now().astimezone().isoformat()
        result_data = {
            "kind": "host_discovery",
            "title": "LIVE HOSTS" if parse_complete else "SCAN INCOMPLETE",
            "scan_status": "ok" if parse_complete else "error",
            "target": str(target),
            "summary": (
                f"{host_count} live host(s) found in {target}"
                if parse_complete
                else "Nmap returned no parseable host-count summary; inspect exact output"
            ),
            "host_count": host_count if parse_complete else None,
            "address_count": reported_count,
            "hosts": hosts if parse_complete else [],
            "own_ip": str(local_address or ""),
            "command": str(result.get("command") or ""),
            "returncode": result.get("returncode"),
            "stdout": stdout,
            "stderr": str(result.get("stderr") or ""),
            "completed_at": completed_at,
            "scan_type": "Nmap host discovery (-sn)",
        }
        self._latest_host_discovery = {
            "target": str(target),
            "hosts": result_data["hosts"],
            "own_ip": str(local_address or ""),
            "completed_at": result_data["completed_at"],
        }
        self._latest_scan_result = result_data
        return result_data

    @staticmethod
    def _build_port_scan_result(
        raw_result: str,
        target: str,
        *,
        host_index: int,
        previous_hosts: list[dict],
        completed_at: str = "",
        host_discovery_target: str = "",
        own_ip: str = "",
    ) -> dict | None:
        result = JenefarOrchestrator._nmap_payload(raw_result)
        if not result:
            return None

        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        returncode = result.get("returncode")
        if returncode != 0:
            completed = completed_at or __import__("datetime").datetime.now().astimezone().isoformat()
            return {
                "kind": "port_scan",
                "title": "SCAN FAILED",
                "scan_status": "error",
                "target": str(target),
                "host_index": int(host_index),
                "summary": f"{target} • Nmap failed (exit code {returncode}); see exact output",
                "command": str(result.get("command") or ""),
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
                "host_status": "ERROR",
                "open_port_count": 0,
                "filtered_port_count": 0,
                "closed_port_count": None,
                "port_scope": "Top 1000 TCP ports",
                "ports": [],
                "hosts": previous_hosts,
                "host_discovery_target": str(host_discovery_target or ""),
                "own_ip": str(own_ip or ""),
                "completed_at": completed,
                "scan_type": "Nmap TCP connect + service detection (-Pn)",
            }
        ports: list[dict] = []
        port_pattern = re.compile(
            r"^\s*(\d{1,5})/(tcp|udp)\s+(open|closed|filtered|open\|filtered)\s+"
            r"([A-Za-z0-9._:+-]+)(?:\s+(.*?))?\s*$",
            re.IGNORECASE,
        )
        for line in stdout.splitlines():
            match = port_pattern.match(line)
            if not match:
                continue
            state = match.group(3).upper()
            # Keep open and filtered states. Closed ports are counted from
            # Nmap's aggregate line instead of listing hundreds of closed rows.
            if state == "CLOSED":
                continue
            ports.append({
                "port": int(match.group(1)),
                "protocol": match.group(2).lower(),
                "state": state,
                "service": match.group(4),
                "version": str(match.group(5) or "").strip(),
            })
        ports.sort(key=lambda item: (item["protocol"], item["port"]))

        open_count = sum(1 for item in ports if item["state"] == "OPEN")
        filtered_count = sum(
            1 for item in ports if item["state"] in {"FILTERED", "OPEN|FILTERED"}
        )
        closed_match = re.search(
            r"Not shown:\s*([0-9,]+)\s+closed\s+tcp\s+ports?",
            stdout,
            re.IGNORECASE,
        )
        closed_count = (
            int(closed_match.group(1).replace(",", "")) if closed_match else None
        )
        filtered_summary_match = re.search(
            r"Not shown:\s*([0-9,]+)\s+filtered\s+tcp\s+ports?",
            stdout,
            re.IGNORECASE,
        )
        if filtered_count == 0 and filtered_summary_match:
            filtered_count = int(filtered_summary_match.group(1).replace(",", ""))

        host_down = bool(re.search(
            r"Host seems down|\b0 hosts up\b",
            stdout,
            re.IGNORECASE,
        ))
        # -Pn deliberately skips ping discovery, so a report header alone does
        # not prove that the host responded. An open port or reported closed
        # TCP ports provide response evidence; filtered-only output does not.
        confirmed_response = open_count > 0 or (closed_count is not None and closed_count > 0)
        host_status = "UNREACHABLE" if host_down else (
            "UP" if confirmed_response else "UNKNOWN"
        )

        if host_status == "UNREACHABLE":
            ports = []
            open_count = 0
            filtered_count = 0
            summary = f"{target} • host reachability not confirmed; port results unavailable"
        else:
            summary = f"{target} • {open_count} open TCP port(s)"
            if filtered_count:
                summary += f", {filtered_count} filtered"
            if host_status == "UNKNOWN":
                summary += "; host reachability not confirmed"

        return {
            "kind": "port_scan",
            "title": "PORT SCAN",
            "target": str(target),
            "host_index": int(host_index),
            "summary": summary,
            "command": str(result.get("command") or ""),
            "returncode": result.get("returncode"),
            "stdout": stdout,
            "stderr": str(result.get("stderr") or ""),
            "host_status": host_status,
            "open_port_count": open_count,
            "filtered_port_count": filtered_count,
            "closed_port_count": closed_count,
            "port_scope": "Top 1000 TCP ports",
            "ports": ports,
            "hosts": previous_hosts,
            "host_discovery_target": str(host_discovery_target or ""),
            "own_ip": str(own_ip or ""),
            "completed_at": completed_at,
            "scan_type": "Nmap TCP connect + service detection (-Pn)",
        }

    @staticmethod
    def _is_ip_info_query(text: str) -> bool:
        """Recognize a direct request for this computer's IP info, not a scan."""
        lowered = " ".join(str(text or "").casefold().split())
        if not lowered or JenefarOrchestrator._is_local_host_discovery_request(lowered):
            return False
        # If the user explicitly asks for scanning, preserve the separate security
        # workflow. A plain "check my IP" request must never be promoted into one.
        scan_markers = (
            "nmap", "masscan", "port scan", "network scan", "subnet scan",
            "scan my network", "scan this network", "open ports", "sweep",
        )
        if any(marker in lowered for marker in scan_markers):
            return False

        import re

        patterns = (
            r"\b(check|show|find|get|display|tell me)\b.{0,40}\b(my|current|public|local)\b.{0,16}\bip(?:v[46])?(?:\s+address)?\b",
            r"\bwhat(?:'s| is)\s+(?:my|the)\s+(?:(?:current|public|local)\s+)?ip(?:v[46])?(?:\s+address)?\b",
            r"\bmy\s+(?:(?:current|public|local)\s+)?ip(?:v[46])?(?:\s+address)?\b",
            r"\b(?:mera|meri)\s+(?:(?:public|local)\s+)?ip(?:\s+address)?\b",
            r"\bip\s+(?:batao|check karo|address kya hai)\b",
        )
        return any(re.search(pattern, lowered) for pattern in patterns)

    def _local_ip_info_response(self) -> str:
        """Return actual local/public IP observations without invoking the LLM or scanner."""
        try:
            raw = self.tool_broker.invoke("network_ip_info", {})
            payload = json.loads(raw)
        except Exception as exc:
            return (
                "IP information check nahi ho paaya. "
                f"Read-only network info tool error: {type(exc).__name__}: {exc}. "
                "Koi network scan execute nahi kiya gaya."
            )

        if not isinstance(payload, dict) or payload.get("status") != "ok":
            error = str(payload.get("error") or "tool returned an invalid result") if isinstance(payload, dict) else "invalid tool result"
            return f"IP information check nahi ho paaya: {error}. Koi network scan execute nahi kiya gaya."

        data = payload.get("result") or {}
        if not isinstance(data, dict):
            return "IP information tool ne invalid data return kiya. Koi network scan execute nahi kiya gaya."

        local_v4 = [
            f"{item.get('address')} ({item.get('interface')})"
            for item in data.get("local_ipv4", [])
            if isinstance(item, dict) and item.get("address")
        ]
        local_v6 = [
            f"{item.get('address')} ({item.get('interface')})"
            for item in data.get("local_ipv6", [])
            if isinstance(item, dict) and item.get("address")
        ]
        public_v4 = str(data.get("public_ipv4") or "").strip()
        lines = ["Aapke computer ki IP information:"]
        lines.append("Local IPv4: " + (", ".join(local_v4) if local_v4 else "active interface address detect nahi hua"))
        if local_v6:
            lines.append("Local IPv6: " + ", ".join(local_v6))
        if public_v4:
            lines.append("Public IPv4: " + public_v4 + " (ipify HTTPS lookup)")
        else:
            lines.append("Public IPv4: abhi fetch nahi ho saka; internet/service unavailable ho sakti hai.")
        lines.append("Bas, IP details yahi hain.")
        return "\n".join(lines)

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

    def _auto_learn_successful_workflow(
        self,
        task: str,
        agent: str,
        actions: list[dict[str, str]],
    ) -> None:
        """Promote verified multi-tool work into persistent memory and a reusable skill.

        Only generic tool names and redacted trigger text are retained; raw arguments,
        results, targets, credentials and private contact details are never saved.
        """
        if len(actions) < 2:
            return
        if str(agent or "").lower() in {"kali", "cybersecurity", "bugbounty", "robotics"}:
            return
        sensitive_markers = (
            "password", "passcode", "api key", "secret", "token",
            "private key", "credential", "one-time password", "otp",
            "bank account", "credit card", "medical record",
        )
        lowered = str(task or "").lower()
        if any(marker in lowered for marker in sensitive_markers):
            return

        tool_names: list[str] = []
        for item in actions:
            name = re.sub(r"[^a-z0-9_]+", "", str(item.get("tool") or "").lower())
            if name and name not in tool_names:
                tool_names.append(name)
        # Do not auto-learn a workflow dominated by outbound, security or physical actions.
        risky_tools = {
            "terminal_execute", "kali_tool_execute", "security_tool_execute",
            "connector_execute", "whatsapp_send_web", "robot_command",
            "robot_mqtt_publish", "robot_ros2_publish",
        }
        if len(tool_names) < 2 or any(name in risky_tools for name in tool_names):
            return

        clean_trigger = str(task or "").strip()
        clean_trigger = re.sub(r"https?://\S+|www\.\S+", "<url>", clean_trigger, flags=re.IGNORECASE)
        clean_trigger = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "<email>", clean_trigger)
        clean_trigger = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b", "<target>", clean_trigger)
        clean_trigger = re.sub(r"(?<!\w)/(?:[^ \t\r\n]+)", "<path>", clean_trigger)
        clean_trigger = " ".join(clean_trigger.split())[:180].strip()
        if len(clean_trigger) < 8:
            return

        slug = re.sub(r"[^a-z0-9]+", "_", clean_trigger.lower()).strip("_")[:36] or "workflow"
        digest = hashlib.sha256(clean_trigger.lower().encode("utf-8")).hexdigest()[:8]
        procedure_name = f"auto_{slug}_{digest}"
        steps = [
            "Use registered tool " + name + " for the corresponding workflow step; inspect its result and verify the postcondition before continuing."
            for name in tool_names[:10]
        ]
        constraints = [
            "This playbook was generated from a previously successful multi-tool task; re-check current inputs and outputs every time.",
            "Never replay old values, paths, IP addresses, credentials or messages from a previous run.",
            "Tool permissions, authorized-target scope, critical-action approvals and user intent always take precedence over this playbook.",
        ]

        try:
            self.memory_engine.save_procedure(
                name=procedure_name,
                trigger_text=clean_trigger,
                steps=steps,
                constraints=constraints,
                source="auto_verified_workflow",
                importance=0.76,
            )
        except Exception as exc:
            print(f"[JENEFAR] Workflow memory save skipped: {type(exc).__name__}: {exc}")

        # Also create a durable Hermes-style SKILL.md for later automatic matching.
        stopwords = {
            "please", "make", "create", "help", "with", "from", "this", "that",
            "what", "when", "where", "your", "my", "meri", "mujhe", "karo",
            "karna", "kar", "do", "and", "the", "for", "into", "using", "use",
            "jenefar", "can", "you", "task", "work", "need", "want", "please",
        }
        raw_keywords = re.findall(r"[a-z0-9_.+-]{3,}", clean_trigger.lower())
        keywords: list[str] = []
        for word in raw_keywords:
            if word in stopwords or word in {"<url>", "<path>", "<target>", "<email>"}:
                continue
            if word not in keywords:
                keywords.append(word)
        if len(keywords) < 2:
            return

        skill_name = f"learned_{slug[:28]}_{digest[:6]}"
        skill_prompt = (
            "Use this automatically learned workflow only when its keywords match the current task. "
            "Begin by checking the current context; do not reuse old input values or assume a previous result is still valid. "
            "Suggested verified tool sequence: " + " -> ".join(tool_names[:10]) + ". "
            "Inspect each tool result and verify the final postcondition. "
            "Never store or request secrets as part of this playbook. "
            "All active user instructions, tool approvals, security scope limits, and system policies take precedence."
        )
        try:
            learned = self.skills.save_learned_skill(
                name=skill_name,
                description="Automatically learned, verified local workflow for: " + clean_trigger[:400],
                keywords=keywords[:12],
                system_prompt=skill_prompt,
                connectors=[],
                permissions=[],
            )
            print(f"[JENEFAR] Learned reusable skill: {learned.get('name', skill_name)}")
        except Exception as exc:
            print(f"[JENEFAR] Automatic skill save skipped: {type(exc).__name__}: {exc}")

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
        approval_id = str(pending_id or "").strip()
        if not approval_id:
            return json.dumps({"status": "error", "error": "approval id required"})

        # A few compatibility tests and embedders construct this object without
        # running __init__; initialize the approval state lazily for those cases.
        approval_lock = getattr(self, "_approval_lock", None)
        if approval_lock is None:
            approval_lock = threading.RLock()
            self._approval_lock = approval_lock
        if not hasattr(self, "_approval_result_cache"):
            self._approval_result_cache = {}

        with approval_lock:
            if approval_id in self._approval_result_cache:
                return self._approval_result_cache[approval_id]

            result = self._approve_pending_once(approval_id)
            if self.state != JenefarState.WAITING_APPROVAL:
                self._finish_waiting_runtime_task(state="completed", reason="Pending approval resolved")
            # Do not cache a transient invalid/expired-ID response. Successful
            # approvals and the associated workflow summary are idempotent.
            if "Unknown or expired pending tool call." not in result:
                self._approval_result_cache[approval_id] = result
                while len(self._approval_result_cache) > 128:
                    oldest_id = next(iter(self._approval_result_cache))
                    self._approval_result_cache.pop(oldest_id, None)
            return result

    def _approve_pending_once(self, pending_id: str) -> str:
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

        if workflow.get("direct_workflow") == "local_host_discovery":
            workflow["remaining"].discard(pending_id)
            self.pending_approval_workflows.pop(pending_id, None)
            summary = self._summarize_local_host_discovery(
                raw_result,
                str(workflow.get("target") or "selected network"),
            )
            result_data = self._record_host_discovery_result(
                raw_result,
                str(workflow.get("target") or "selected network"),
                summary,
                local_address=str(workflow.get("local_address") or ""),
            )
            avatar = getattr(self, "avatar", None)
            if result_data and avatar is not None:
                avatar.publish("scan_results", str(result_data["summary"]), data=result_data)
            self.session.add("assistant", summary)
            self.memory_engine.record_message(
                self.session.session_id,
                "assistant",
                summary,
                importance=0.65,
            )
            self.graph.learn_text(summary)
            self.state = (
                JenefarState.SLEEPING
                if self.config.single_turn_sleep
                else JenefarState.AWAKE
            )
            # The caller owns speech playback (browser audio/TTS or CLI output).
            # Publishing another speech event here caused duplicate voice playback.
            return summary

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
