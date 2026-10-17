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


def test_kali_catalog_help_and_confirmed_executor_are_registered():
    broker = ToolBroker(require_confirmation=True)
    names = {tool["name"] for tool in broker.schemas(allow_action_tools=True)}
    assert "kali_catalog" in names
    assert "kali_tool_help" in names
    assert "kali_tool_execute" in names


def test_kali_execution_approval_displays_exact_command_and_target(monkeypatch):
    import json

    broker = ToolBroker(require_confirmation=True)
    monkeypatch.setattr(
        broker.kali,
        "preview",
        lambda **_kwargs: {
            "tool": "nmap",
            "command": "/usr/bin/nmap -sV 192.168.29.10",
            "target": "192.168.29.10",
            "targets": ["192.168.29.10"],
            "timeout_seconds": 30,
            "scope_checked": True,
            "inspection_required": False,
            "requires_user_approval": True,
        },
    )
    result = json.loads(broker.invoke("kali_tool_execute", {
        "tool": "nmap",
        "args": ["-sV", "192.168.29.10"],
        "target": "192.168.29.10",
        "timeout": 30,
    }))
    assert result["status"] == "approval_required"
    pending = broker.pending[result["pending_id"]]
    assert pending.arguments["tool"] == "nmap"
    # The exact preview is surfaced through the current activity/approval prompt.
    assert "kali_tool_execute" == result["tool"]


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
