from pathlib import Path

from jenefar.voice.wakeword_trainer import prepare_config


def test_prepare_wakeword_config(tmp_path: Path):
    path = prepare_config("Hi Jenefar", output_dir=str(tmp_path))
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Hi Jenefar" in text
    assert "feature_data_files: {}" in text
    assert "ACAV100M" not in text
