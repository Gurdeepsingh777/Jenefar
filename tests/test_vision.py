from pathlib import Path
from jenefar.core.planner import Planner
from jenefar.vision.screen import ScreenFrame, ScreenVision


class FakeDesktop:
    pass


def test_vision_parser_scales_coordinates_and_filters_low_confidence():
    frame = ScreenFrame(
        png_bytes=b"png",
        width=1920,
        height=1080,
        encoded_width=960,
        encoded_height=540,
    )
    vision = ScreenVision(FakeDesktop(), confidence_threshold=0.65)
    payload = {
        "elements": [
            {
                "label": "Search box",
                "role": "textbox",
                "confidence": 0.95,
                "bbox": [100, 50, 300, 150],
                "text": "Search",
            },
            {
                "label": "Weak",
                "role": "button",
                "confidence": 0.4,
                "bbox": [10, 10, 20, 20],
            },
        ]
    }
    elements = vision._parse_elements(payload, frame)
    assert len(elements) == 1
    assert elements[0].center == (400, 200)
    assert elements[0].bbox == (200, 100, 600, 300)


def test_vision_parser_rejects_missing_elements_shape():
    frame = ScreenFrame(
        png_bytes=b"png",
        width=100,
        height=100,
        encoded_width=100,
        encoded_height=100,
    )
    vision = ScreenVision(FakeDesktop())
    try:
        vision._parse_elements({"elements": {}}, frame)
    except ValueError as exc:
        assert "must be a list" in str(exc)
    else:
        raise AssertionError("Expected invalid elements shape to raise")


def test_planner_routes_semantic_screen_requests():
    plan = Planner().plan("find the search box on screen and click it")
    assert plan.agent == "gui_vision"
    assert plan.intent == "semantic_gui"


def test_planner_routes_natural_screen_read_phrasing():
    phrases = (
        "screen par kya dikh raha hai",
        "meri screen pe kya hai",
        "read my screen",
        "screen pe mujhe kya dikh raha hai",
    )
    for phrase in phrases:
        plan = Planner().plan(phrase)
        assert plan.agent == "gui_vision"
        assert plan.intent == "semantic_gui"


def test_screen_vision_prefers_local_vlm_without_online_credits(monkeypatch):
    from jenefar.vision.screen import ScreenFrame, ScreenVision

    class FakeDesktop:
        def capture_frame(self, *, max_dimension, save):
            return ScreenFrame(
                png_bytes=b"png",
                width=1920,
                height=1080,
                encoded_width=1600,
                encoded_height=900,
                path=None,
            )

    vision = ScreenVision(FakeDesktop())
    monkeypatch.delenv("JENEFAR_VISION_ALLOW_ONLINE", raising=False)
    monkeypatch.setattr(
        vision,
        "_local_analyze",
        lambda _frame, _task: {
            "summary": "Local screen analysis",
            "elements": [{
                "label": "Browser",
                "role": "window",
                "confidence": 0.95,
                "bbox": [0, 0, 100, 100],
                "text": "Chrome",
            }],
        },
    )

    def fail_online(*_args, **_kwargs):
        raise AssertionError("Online vision should not be called by default.")

    monkeypatch.setattr(vision, "_online_analyze", fail_online)
    result = vision.analyze("screen par kya dikh raha hai?")
    assert result["provider"] == "local_ollama"
    assert result["summary"] == "Local screen analysis"
    assert result["elements"][0]["label"] == "Browser"


def test_screen_vision_rejects_text_only_local_model_selection():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "jenefar" / "vision" / "screen.py").read_text(encoding="utf-8")
    assert "qwen3-vl:4b" in source
    assert "llama3.2:latest" in source
    assert "must not be used for screen vision" in source
    assert "JENEFAR_VISION_ALLOW_ONLINE" in source


def test_screen_vision_summary_prompt_is_user_facing_and_concise():
    source = (Path(__file__).resolve().parents[1] / "jenefar" / "vision" / "screen.py").read_text(encoding="utf-8")
    assert "1-3 short natural sentences" in source
    assert "Do not read out file paths" in source
    assert "Do not speculate" in source


def test_provider_defaults_do_not_depend_on_obsolete_gemini_model():
    source = (Path(__file__).resolve().parents[1] / "jenefar" / "core" / "provider_pool.py").read_text(encoding="utf-8")
    assert "gemini-3.5-flash-lite" in source
    assert "gemini-2.5-flash-lite" in source
    assert "openrouter/free" in source
