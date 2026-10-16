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


def test_installed_skill_manifest_is_discovered_without_restart(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    manager = SkillManager(tmp_path / "state.json", skill_roots=[root])
    manifest = root / "cad.json"
    manifest.write_text(
        '{"name":"cad","version":"1.0","description":"CAD helper.","enabled_by_default":true}',
        encoding="utf-8",
    )
    assert any(item["name"] == "cad" and item["enabled"] for item in manager.list())


def test_hermes_style_skill_md_is_discovered_as_declarative_text(tmp_path: Path):
    root = tmp_path / "skills"
    folder = root / "sample-helper"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        '---\nname: sample_helper\ndescription: A local helper skill.\nkeywords:\n  - sample\n  - helper\n---\nUse registered tools only.',
        encoding="utf-8",
    )
    manager = SkillManager(tmp_path / "state.json", skill_roots=[root])
    skill = manager.get("sample_helper")
    assert skill.description == "A local helper skill."
    assert skill.system_prompt == "Use registered tools only."
    assert manager.is_enabled("sample_helper") is True


def test_hermes_skill_does_not_import_executable_code(tmp_path: Path):
    root = tmp_path / "skills"
    folder = root / "sample-helper"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        '---\nname: sample_helper\ndescription: A local helper skill.\n---\nDo not bypass user permissions.',
        encoding="utf-8",
    )
    manager = SkillManager(tmp_path / "state.json", skill_roots=[root])
    assert manager.get("sample_helper").source.endswith("SKILL.md")
