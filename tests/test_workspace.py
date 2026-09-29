from pathlib import Path

from jenefar.workspace.policy import WorkspacePolicy
from jenefar.workspace.service import WorkspaceService


def test_workspace_policy_accepts_root_and_child(tmp_path: Path):
    policy = WorkspacePolicy([str(tmp_path)])
    assert policy.allowed(tmp_path)
    assert policy.allowed(tmp_path / "example.py")
    assert not policy.allowed(tmp_path.parent / "outside.py")


def test_workspace_edit_creates_backup_and_diff(tmp_path: Path):
    path = tmp_path / "example.py"
    path.write_text("print('old')\n", encoding="utf-8")
    service = WorkspaceService(WorkspacePolicy([str(tmp_path)]))

    result = service.edit_file(str(path), "print('new')\n")

    assert path.read_text(encoding="utf-8") == "print('new')\n"
    assert Path(result["backup"]).is_file()
    assert "old" in result["diff"]
    assert "new" in result["diff"]
