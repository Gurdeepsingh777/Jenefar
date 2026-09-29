import json

from jenefar.execution.scope import ScopePolicy
from jenefar.tools.broker import ToolBroker


def test_action_tools_are_hidden_by_default():
    broker = ToolBroker(scope=ScopePolicy(["192.168.1.0/24"]))
    names = {item["name"] for item in broker.schemas()}
    assert "desktop_click" not in names
    assert "robot_command" not in names
    assert "security_tool_execute" not in names


def test_action_tools_are_available_to_action_enabled_agents():
    broker = ToolBroker(scope=ScopePolicy(["192.168.1.0/24"]))
    names = {item["name"] for item in broker.schemas(allow_action_tools=True)}
    assert "desktop_click" in names
    assert "robot_command" in names
    assert "security_tool_execute" in names


def test_action_tool_requires_approval():
    broker = ToolBroker(scope=ScopePolicy(["192.168.1.0/24"]))
    result = json.loads(
        broker.invoke(
            "robot_command",
            {"command": "stop", "argument": ""},
        )
    )
    assert result["status"] == "approval_required"
