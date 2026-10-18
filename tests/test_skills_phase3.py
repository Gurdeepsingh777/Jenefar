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


def test_learned_skill_is_persisted_and_auto_enabled(tmp_path: Path):
    root = tmp_path / "skills"
    manager_state = tmp_path / "skills-state.json"
    manager = SkillManager(manager_state, skill_roots=[root])
    result = manager.save_learned_skill(
        name="learned_python_test_workflow",
        description="A reusable workflow for local Python test validation.",
        keywords=["python", "pytest", "validation"],
        system_prompt="Inspect current project state, run the registered test workflow, and verify results.",
        connectors=[],
        permissions=[],
    )
    assert result["saved"] is True
    assert result["enabled"] is True
    assert result["executable_code_installed"] is False
    assert Path(result["path"]).name == "SKILL.md"

    manager_after_restart = SkillManager(manager_state, skill_roots=[root])
    learned = manager_after_restart.get("learned_python_test_workflow")
    assert manager_after_restart.is_enabled("learned_python_test_workflow") is True
    assert "verify results" in learned.system_prompt
    assert Path(learned.source).is_file()



def test_skill_catalog_summary_hides_full_skill_prompt_and_local_source():
    from jenefar.tools.broker import ToolBroker

    listed = ToolBroker._skill_catalog_summary([{
        "name": "rea_ci_tests_audit",
        "version": "1.0",
        "description": "Audit CI test results.",
        "keywords": ["ci", "tests"],
        "connectors": ["github"],
        "permissions": ["repository_read"],
        "enabled": True,
        "available": True,
        "system_prompt": "A very long private prompt body that should not be returned.",
        "source": "/home/user/project/skills/private/SKILL.md",
    }])

    assert listed == [{
        "name": "rea_ci_tests_audit",
        "version": "1.0",
        "description": "Audit CI test results.",
        "keywords": ["ci", "tests"],
        "connectors": ["github"],
        "permissions": ["repository_read"],
        "enabled": True,
        "available": True,
    }]
