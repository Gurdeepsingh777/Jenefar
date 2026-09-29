from pathlib import Path

from jenefar.agents.coding.local_development import LocalDevelopmentAgent
from jenefar.workspace.policy import WorkspacePolicy
from jenefar.workspace.service import WorkspaceService


def test_local_development_agent_has_bounded_self_healing_policy():
    assert LocalDevelopmentAgent.model_role == "coding"
    assert LocalDevelopmentAgent.max_tool_rounds >= 10
    assert "self-healing" in LocalDevelopmentAgent.system_prompt


def test_workspace_validate_python(tmp_path: Path):
    path = tmp_path / "example.py"
    path.write_text("print('ok')\n", encoding="utf-8")
    result = WorkspaceService(WorkspacePolicy([str(tmp_path)])).validate_python(str(path))
    assert result["valid"] is True


def test_workspace_validate_python_reports_syntax_error(tmp_path: Path):
    path = tmp_path / "broken.py"
    path.write_text("if True print('broken')\n", encoding="utf-8")
    result = WorkspaceService(WorkspacePolicy([str(tmp_path)])).validate_python(str(path))
    assert result["valid"] is False
    assert result["returncode"] != 0
