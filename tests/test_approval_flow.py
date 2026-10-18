import json
import time
from concurrent.futures import ThreadPoolExecutor

from jenefar.core.agent import AgentResult
from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.core.state import JenefarState


class FakeAgent:
    name = "python"

    def __init__(self):
        self.continued_with = None
        self.continue_calls = 0

    def continue_after_tools(self, task, tool_results):
        self.continue_calls += 1
        self.continued_with = (task, tool_results)
        return AgentResult(
            agent=self.name,
            content=f"finalized: {tool_results[0]['result']}",
            metadata={"provider": "fake"},
        )


class FakeRouter:
    def __init__(self, agent):
        self.agent = agent

    def agent_by_name(self, name):
        return self.agent if name == self.agent.name else None

    def dispatch(self, *args, **kwargs):
        return AgentResult(
            agent=self.agent.name,
            content="approval pending",
            metadata={
                "provider": "approval_required",
                "pending_tools": [
                    {
                        "pending_id": "pending-1",
                        "tool": "local_action",
                        "call_id": "call-1",
                    }
                ],
            },
        )


class FakeBroker:
    def __init__(self):
        self.approve_calls = 0

    def approve(self, pending_id):
        assert pending_id == "pending-1"
        self.approve_calls += 1
        # Keep the tool call in flight long enough to exercise concurrent approvals.
        time.sleep(0.03)
        return json.dumps({
            "status": "ok",
            "result": "TEST_OUTPUT",
            "tool": "local_action",
        })


def test_approval_resumes_with_final_answer():
    orchestrator = JenefarOrchestrator()
    fake_agent = FakeAgent()
    orchestrator.router = FakeRouter(fake_agent)
    orchestrator.tool_broker = FakeBroker()

    pending_answer = orchestrator.handle("run the tests")
    assert pending_answer == "approval pending"
    assert orchestrator.state == JenefarState.WAITING_APPROVAL

    final_answer = orchestrator._approve_pending("pending-1")
    assert "TEST_OUTPUT" in final_answer
    assert orchestrator.state == JenefarState.SLEEPING
    assert fake_agent.continued_with[0] == "run the tests"
    assert orchestrator.tool_broker.approve_calls == 1
    assert fake_agent.continue_calls == 1


def test_duplicate_concurrent_approvals_execute_and_resume_only_once():
    orchestrator = JenefarOrchestrator()
    fake_agent = FakeAgent()
    broker = FakeBroker()
    orchestrator.router = FakeRouter(fake_agent)
    orchestrator.tool_broker = broker

    assert orchestrator.handle("run the tests") == "approval pending"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(orchestrator._approve_pending, "pending-1")
        second = pool.submit(orchestrator._approve_pending, "pending-1")
        first_result = first.result(timeout=5)
        second_result = second.result(timeout=5)

    assert first_result == second_result
    assert "TEST_OUTPUT" in first_result
    assert broker.approve_calls == 1
    assert fake_agent.continue_calls == 1


def test_local_host_discovery_approval_has_one_speech_owner():
    orchestrator = JenefarOrchestrator()
    states = []

    class HostDiscoveryBroker:
        def __init__(self):
            self.approve_calls = 0

        def approve(self, pending_id):
            assert pending_id == "pending-host-1"
            self.approve_calls += 1
            return json.dumps({
                "status": "ok",
                "tool": "kali_tool_execute",
                "result": {
                    "returncode": 0,
                    "stdout": "Nmap done: 256 IP addresses (4 hosts up) scanned in 2.20 seconds",
                    "stderr": "",
                },
            })

    broker = HostDiscoveryBroker()
    orchestrator.tool_broker = broker
    orchestrator.pending_approval_workflows["pending-host-1"] = {
        "direct_workflow": "local_host_discovery",
        "target": "192.168.29.0/24",
        "remaining": {"pending-host-1"},
        "results": [],
    }
    orchestrator.memory_engine.record_message = lambda *_args, **_kwargs: None
    orchestrator.graph.learn_text = lambda *_args, **_kwargs: None
    orchestrator._avatar_state = lambda state, text="": states.append((state, text))

    first = orchestrator._approve_pending("pending-host-1")
    second = orchestrator._approve_pending("pending-host-1")

    assert "4 host(s) online" in first
    assert second == first
    assert broker.approve_calls == 1
    assert states == []
