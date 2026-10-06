from __future__ import annotations

from pathlib import Path

import pytest

from jenefar.production.readiness import check
from jenefar.browser.playwright_adapter import PlaywrightComputerAdapter


def test_readiness_requires_remote_auth_and_tls(monkeypatch, tmp_path):
    monkeypatch.setenv("JENEFAR_HOST", "0.0.0.0")
    monkeypatch.setenv("JENEFAR_AUTH_USER", "")
    monkeypatch.setenv("JENEFAR_AUTH_PASSWORD", "")
    monkeypatch.delenv("JENEFAR_TLS_CERT", raising=False)
    monkeypatch.delenv("JENEFAR_TLS_KEY", raising=False)
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "")
    result = check()
    assert result["ready"] is False
    assert any("remote deployment requires" in item for item in result["failures"])


def test_readiness_explicit_approval_secret(monkeypatch):
    monkeypatch.setenv("JENEFAR_REQUIRE_EXPLICIT_APPROVAL_SECRET", "1")
    monkeypatch.delenv("JENEFAR_APPROVAL_SECRET", raising=False)
    monkeypatch.setenv("JENEFAR_HOST", "127.0.0.1")
    result = check()
    assert any("JENEFAR_APPROVAL_SECRET" in item for item in result["failures"])


class FakeLocator:
    def __init__(self, text="hello"):
        self.text = text
    def inner_text(self, timeout=3000):
        return self.text


class FakePage:
    url = "http://example.test/"
    def title(self):
        return "Example"
    def locator(self, _selector):
        return FakeLocator()
    def goto(self, url, wait_until="domcontentloaded"):
        self.url = url
    def get_by_role(self, role, name, exact=True):
        return self
    def click(self):
        self.url = self.url + "#clicked"
    def get_by_text(self, text, exact=True):
        return self
    def get_by_label(self, label, exact=True):
        return self
    def fill(self, value):
        return None
    class keyboard:
        @staticmethod
        def press(key):
            return None
    def screenshot(self, path, full_page=True):
        Path(path).write_bytes(b"test")


def test_playwright_adapter_structured_actions(tmp_path):
    page = FakePage()
    adapter = PlaywrightComputerAdapter(page)
    before = adapter.observe()
    after = adapter.act({"type": "goto", "url": "http://example.test/new", "expected_url": "new"})
    assert adapter.verify(before, after, {"type": "goto", "expected_url": "new"})
    shot = tmp_path / "browser.png"
    result = adapter.act({"type": "screenshot", "path": str(shot)})
    assert shot.exists()
    assert adapter.verify(after, result, {"type": "screenshot"})
