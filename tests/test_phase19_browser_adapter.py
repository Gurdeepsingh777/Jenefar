from __future__ import annotations

import pytest

from jenefar.browser.playwright_adapter import PlaywrightComputerAdapter


class Locator:
    def inner_text(self, timeout=3000):
        return "test page"


class FakePage:
    def __init__(self):
        self.url = "https://example.org/"
        self.visited = []
        self.screenshots = []
        self.keyboard = type("Keyboard", (), {"press": lambda _self, _key: None})()

    def title(self):
        return "Example"

    def locator(self, _selector):
        return Locator()

    def goto(self, url, wait_until):
        self.visited.append((url, wait_until))
        self.url = url

    def screenshot(self, path, full_page):
        self.screenshots.append((path, full_page))


def test_browser_adapter_rejects_loopback_navigation_by_default():
    page = FakePage()
    adapter = PlaywrightComputerAdapter(page)
    with pytest.raises(PermissionError):
        adapter.act({"type": "goto", "url": "http://127.0.0.1:11434"})
    assert page.visited == []


def test_browser_adapter_can_explicitly_allow_private_hosts():
    page = FakePage()
    adapter = PlaywrightComputerAdapter(page, allow_private_hosts=True)
    result = adapter.act({"type": "goto", "url": "http://127.0.0.1:8080"})
    assert result["url"] == "http://127.0.0.1:8080"
    assert page.visited == [("http://127.0.0.1:8080", "domcontentloaded")]


def test_browser_adapter_enforces_configured_origin_allowlist():
    page = FakePage()
    adapter = PlaywrightComputerAdapter(page, allowed_origins=("https://safe.example",))
    with pytest.raises(PermissionError):
        adapter.act({"type": "goto", "url": "https://example.org/path"})
    assert page.visited == []


def test_browser_adapter_screenshot_path_stays_inside_root(tmp_path):
    page = FakePage()
    root = tmp_path / "screenshots"
    adapter = PlaywrightComputerAdapter(page, screenshot_root=root)
    adapter.act({"type": "screenshot", "path": str(root / "ok.png")})
    assert page.screenshots[0][0] == str(root / "ok.png")
    with pytest.raises(PermissionError):
        adapter.act({"type": "screenshot", "path": str(tmp_path / "outside.png")})
