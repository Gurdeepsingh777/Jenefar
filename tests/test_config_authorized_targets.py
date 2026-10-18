from __future__ import annotations

from pathlib import Path

import jenefar.core.config as config_module


def test_load_config_merges_yaml_env_and_dotenv_authorized_targets(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "security:\n"
        "  authorized_targets:\n"
        "    - 192.168.1.0/24\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "JENEFAR_AUTHORIZED_TARGETS=192.168.29.0/24,10.20.30.40\n",
        encoding="utf-8",
    )
    # Simulate a parent process exporting the key as an empty string; python-dotenv
    # won't override that with load_dotenv(override=False), but the file is explicit.
    monkeypatch.setenv("JENEFAR_AUTHORIZED_TARGETS", "")

    config = config_module.load_config()

    assert config.authorized_targets == [
        "192.168.1.0/24",
        "192.168.29.0/24",
        "10.20.30.40",
    ]


def test_load_config_reads_environment_targets_without_yaml_scope(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text("security:\n  authorized_targets: []\n", encoding="utf-8")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    monkeypatch.setenv("JENEFAR_AUTHORIZED_TARGETS", "192.168.29.0/24")

    config = config_module.load_config()

    assert config.authorized_targets == ["192.168.29.0/24"]
