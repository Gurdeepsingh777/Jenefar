from pathlib import Path

from jenefar.skills.manager import SkillManager
from jenefar.skills.manifest import SkillManifest


def test_builtin_skills_are_available(tmp_path: Path):
    manager = SkillManager(tmp_path / "skills.json")
    names = {item["name"] for item in manager.list()}
    assert "local_development" in names
    assert "gui_vision" in names


def test_skill_enable_disable_persists(tmp_path: Path):
    manager = SkillManager(tmp_path / "skills.json")
    manager.disable("gui_vision")
    assert manager.is_enabled("gui_vision") is False
    manager2 = SkillManager(tmp_path / "skills.json")
    assert manager2.is_enabled("gui_vision") is False
    manager2.enable("gui_vision")
    assert manager2.is_enabled("gui_vision") is True


def test_skill_manifest_validation():
    manifest = SkillManifest.from_dict(
        {
            "name": "blender",
            "version": "1.0",
            "description": "Blender automation.",
            "keywords": ["blender", "render"],
            "connectors": ["desktop"],
            "permissions": ["gui_action"],
        }
    )
    assert manifest.name == "blender"
    assert manifest.connectors == ("desktop",)


def test_skill_install_is_root_scoped(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    manifest_path = root / "blender.json"
    manifest_path.write_text(
        '{"name":"blender","version":"1.0","description":"Blender automation."}',
        encoding="utf-8",
    )
    manager = SkillManager(tmp_path / "state.json", skill_roots=[root])
    result = manager.install_manifest(str(manifest_path))
    assert result["installed"] is True
    assert manager.is_enabled("blender") is True
