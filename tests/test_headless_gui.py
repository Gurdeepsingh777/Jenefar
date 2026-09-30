from jenefar.automation.headless import HeadlessDesktopAutomation
from jenefar.vision.screen import ScreenVision


def test_headless_gui_path_needs_no_pyautogui_or_vision_model():
    desktop = HeadlessDesktopAutomation()
    vision = ScreenVision(desktop)

    observed = vision.analyze("find the search box")
    assert observed["provider"] == "headless_fixture"
    assert observed["screen"] == {"width": 1280, "height": 720}
    assert any(item["label"] == "Search box" for item in observed["elements"])

    located = vision.locate("search box")
    assert located["match"]["center"] == (410, 137)

    clicked = vision.locate_and_click("search box")
    assert clicked["action"]["target"] == "Search box"

    typed = vision.locate_and_type("search box", "Jenefar AI")
    assert typed["type"]["text"] == "Jenefar AI"


def test_headless_submit_changes_virtual_state():
    desktop = HeadlessDesktopAutomation()
    vision = ScreenVision(desktop)

    vision.locate_and_click("submit button")
    observed = vision.analyze("submit button")
    submit = next(item for item in observed["elements"] if item["label"] == "Submit button")
    assert submit["text"] == "Submitted"
