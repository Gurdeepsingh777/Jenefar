import json

from jenefar.core.agent import AgentResult
from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.core.state import JenefarState


class FakeAgent:
    name = "python"

    def __init__(self):
        self.continued_with = None

    def continue_after_tools(self, task, tool_results):
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
    def approve(self, pending_id):
        assert pending_id == "pending-1"
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
