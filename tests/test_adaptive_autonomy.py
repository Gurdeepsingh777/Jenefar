import json
from pathlib import Path

from jenefar.tools.broker import ToolBroker
from jenefar.workspace.policy import WorkspacePolicy
from jenefar.workspace.service import WorkspaceService


WORKSPACE_AUTO_TOOLS = (
    "workspace_inspect_file",
    "workspace_list_directory",
    "workspace_edit_file",
    "workspace_create_file",
    "workspace_validate_python",
    "workspace_run_python",
    "workspace_run_pytest",
)

GATED_TOOLS = (
    "terminal_execute",
    "kali_tool_execute",
    "security_tool_execute",
    "robot_command",
    "robot_mqtt_publish",
    "robot_ros2_publish",
    "connector_execute",
    "desktop_click_element",
    "desktop_click",
    "desktop_type",
    "desktop_screenshot",
)


def test_workspace_tools_are_not_critical():
    broker = ToolBroker(require_confirmation=False)
    for name in WORKSPACE_AUTO_TOOLS:
        spec = broker.registry.get(name)
        assert spec.critical is False, name


def test_gated_tools_are_critical():
    broker = ToolBroker(require_confirmation=False)
    for name in GATED_TOOLS:
        spec = broker.registry.get(name)
        assert spec.critical is True, name


def test_workspace_edit_runs_without_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("JENEFAR_WORKSPACE_ROOTS", str(tmp_path))
    path = tmp_path / "example.py"
    path.write_text("print('old')\n", encoding="utf-8")
    broker = ToolBroker(require_confirmation=False)
    broker.workspace = WorkspaceService(WorkspacePolicy([str(tmp_path)]))
    result = json.loads(broker.invoke("workspace_edit_file", {
        "path": str(path),
        "new_content": "print('new')\n",
    }))
    assert result["status"] == "ok"
    assert path.read_text(encoding="utf-8") == "print('new')\n"


def test_workspace_run_python_runs_without_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("JENEFAR_WORKSPACE_ROOTS", str(tmp_path))
    path = tmp_path / "hello.py"
    path.write_text("print('jenefar')\n", encoding="utf-8")
    broker = ToolBroker(require_confirmation=False)
    broker.workspace = WorkspaceService(WorkspacePolicy([str(tmp_path)]))
    result = json.loads(broker.invoke("workspace_run_python", {
        "path": str(path),
        "timeout": 5,
    }))
    assert result["status"] == "ok"
    assert "jenefar" in str(result["result"])


def test_path_outside_workspace_is_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("JENEFAR_WORKSPACE_ROOTS", str(tmp_path))
    outside = Path("/tmp/jenefar-outside-autonomy.py")
    broker = ToolBroker(require_confirmation=False)
    broker.workspace = WorkspaceService(WorkspacePolicy([str(tmp_path)]))
    result = json.loads(broker.invoke("workspace_inspect_file", {"path": str(outside)}))
    assert result["status"] == "error"
    assert "outside" in str(result.get("error", "")).lower() or "scope" in str(result.get("error", "")).lower()


def test_terminal_still_requires_approval_when_confirmation_off():
    broker = ToolBroker(require_confirmation=False)
    result = json.loads(broker.invoke("terminal_execute", {"command": "printf jenefar", "timeout": 5}))
    assert result["status"] == "approval_required"
    assert result["critical"] is True
