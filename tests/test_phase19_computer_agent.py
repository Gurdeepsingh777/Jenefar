from __future__ import annotations

from jenefar.browser.computer_agent import ComputerAgent


class FakeAdapter:
    def __init__(self):
        self.state = {"step": 0}

    def observe(self):
        return dict(self.state)

    def act(self, action):
        self.state = {"step": self.state["step"] + 1, "action": action["type"]}
        return dict(self.state)

    def verify(self, before, after, action):
        return after["step"] > before["step"]


def test_computer_agent_stops_after_verified_terminal_action():
    adapter = FakeAdapter()
    agent = ComputerAgent(adapter, max_steps=8)
    planned = []

    def planner(goal, observation, steps):
        planned.append((goal, observation["step"], len(steps)))
        return {"type": "finish", "terminal": True}

    steps = agent.execute(planner, "finish a safe test task")
    assert len(steps) == 1
    assert steps[0].verified is True
    assert len(planned) == 1


def test_computer_agent_enforces_step_budget():
    adapter = FakeAdapter()
    agent = ComputerAgent(adapter, max_steps=2)
    steps = agent.execute(lambda goal, observation, history: {"type": "next"}, "test")
    assert len(steps) == 2
    assert all(step.verified for step in steps)


def test_computer_agent_records_adapter_errors_without_claiming_success():
    class BrokenAdapter(FakeAdapter):
        def act(self, action):
            raise RuntimeError("adapter offline")

    steps = ComputerAgent(BrokenAdapter(), max_steps=3).execute(
        lambda goal, observation, history: {"type": "click"},
        "click a test target",
    )
    assert len(steps) == 1
    assert steps[0].verified is False
    assert "adapter offline" in (steps[0].error or "")
