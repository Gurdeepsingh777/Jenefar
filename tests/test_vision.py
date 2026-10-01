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
