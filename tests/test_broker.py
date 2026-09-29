from jenefar.tools.broker import ToolBroker

def test_discover_tool_is_exposed_without_confirmation():
    broker = ToolBroker(require_confirmation=True)
    names = {tool["name"] for tool in broker.schemas()}
    assert "discover_kali_tools" in names
    assert "terminal_execute" not in names

def test_terminal_requires_explicit_confirmation():
    broker = ToolBroker(require_confirmation=True)
    result = broker.invoke("terminal_execute", {"command": "echo jenefar", "timeout": 5})
    assert '"status": "approval_required"' in result
    assert len(broker.pending) == 1

def test_pending_terminal_can_be_approved():
    broker = ToolBroker(require_confirmation=True)
    request = broker.invoke("terminal_execute", {"command": "printf test", "timeout": 5})
    import json
    pending_id = json.loads(request)["pending_id"]
    result = json.loads(broker.approve(pending_id))
    assert result["status"] == "ok"
    assert "test" in result["result"]
