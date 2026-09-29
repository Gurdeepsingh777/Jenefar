from jenefar.core.agent import AgentContext, AgentResult, FunctionAgent
from jenefar.tools.safety import ToolPolicy, ToolRequest


def test_function_agent():
    agent = FunctionAgent(
        "demo", "demo", lambda ctx: ctx.task.upper(), lambda text: "demo" in text.lower()
    )
    assert agent.can_handle("demo task")
    result = agent.run(AgentContext("hello"))
    assert isinstance(result, AgentResult)
    assert result.content == "HELLO"


def test_tool_policy_requires_confirmation():
    policy = ToolPolicy(True)
    request = ToolRequest("terminal", {}, requires_confirmation=True)
    assert not policy.authorize(request)
    assert policy.authorize(request, confirmed=True)
