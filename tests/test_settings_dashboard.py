from pathlib import Path

from jenefar.avatar.settings import UISettings
from jenefar.evaluation.dashboard import render_dashboard


def test_ui_settings_only_persists_allowlisted_values(tmp_path: Path):
    settings = UISettings(tmp_path / "settings.json")
    value = settings.update({
        "theme": "dark",
        "avatar_port": 9000,
        "OPENAI_API_KEY": "must-not-persist",
    })
    assert value["theme"] == "dark"
    assert "OPENAI_API_KEY" not in value


def test_dashboard_renders_empty_state(tmp_path: Path):
    html = render_dashboard(tmp_path / "eval.jsonl")
    assert "Jenefar Evaluation Dashboard" in html
