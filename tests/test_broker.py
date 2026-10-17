from jenefar.tools.broker import ToolBroker

def test_discover_tool_is_exposed_without_confirmation():
    broker = ToolBroker(require_confirmation=True)
    names = {tool["name"] for tool in broker.schemas()}
    assert "discover_kali_tools" in names
    assert "terminal_execute" in names

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


def test_rea_tools_are_registered_and_mutating_bridge_call_is_gated(monkeypatch):
    import json

    monkeypatch.setenv("JENEFAR_REA_ENABLED", "false")
    broker = ToolBroker(require_confirmation=True)
    names = {tool["name"] for tool in broker.schemas(allow_action_tools=True)}
    assert "rea_status" in names
    assert "rea_list_tools" in names
    assert "rea_call" in names

    result = json.loads(broker.invoke("rea_call", {"tool": "inspect_binary_layout", "arguments": {"path": "/tmp/example.elf"}}))
    assert result["status"] == "approval_required"
    assert result["tool"] == "rea_call"
    assert len(broker.pending) == 1
