from pathlib import Path

from jenefar.core.planner import Planner
from jenefar.skills.manager import SkillManager


def test_planner_falls_back_when_required_skill_is_disabled(tmp_path: Path):
    skills = SkillManager(tmp_path / "skills.json")
    skills.disable("gui_vision")
    plan = Planner(skills=skills).plan("find the search box on screen")
    assert plan.agent == "research"
    assert "gui_vision" in plan.reason


def test_skill_prompt_context_contains_enabled_skill(tmp_path: Path):
    skills = SkillManager(tmp_path / "skills.json")
    context = skills.prompt_context()
    assert "local_development" in context
