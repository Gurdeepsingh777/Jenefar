import json

from jenefar.execution.scope import ScopePolicy
from jenefar.tools.broker import ToolBroker

def test_scope_check_tool():
    broker = ToolBroker(scope=ScopePolicy(["192.168.1.0/24"]))
    result = json.loads(broker.invoke("scope_check", {"target": "192.168.1.50"}))
    assert result["status"] == "ok"
    assert result["result"]["allowed"] is True

def test_terminal_schema_is_exposed_but_still_requires_approval():
    broker = ToolBroker(require_confirmation=True)
    names = {x["name"] for x in broker.schemas()}
    assert "terminal_execute" in names
    result = json.loads(
        broker.invoke("terminal_execute", {"command": "echo ok", "timeout": 5})
    )
    assert result["status"] == "approval_required"
