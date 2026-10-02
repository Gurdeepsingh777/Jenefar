from pathlib import Path


def test_local_vision_timeout_is_configurable():
    source = Path("jenefar/vision/screen.py").read_text()

    assert "JENEFAR_LOCAL_VISION_TIMEOUT_SECONDS" in source
    assert "timeout=min(" in source
    assert "600.0" in source


def test_default_local_vision_model_remains_qwen3_vl():
    source = Path("jenefar/vision/screen.py").read_text()

    assert "qwen3-vl:4b" in source
