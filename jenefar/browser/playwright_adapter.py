from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlaywrightComputerAdapter:
    """Real Chromium adapter for the ComputerAgent contract."""

    page: Any

    def observe(self) -> dict[str, Any]:
        return {
            "url": self.page.url,
            "title": self.page.title(),
            "text": self.page.locator("body").inner_text(timeout=3000)[:8000],
        }

    def act(self, action: dict[str, Any]) -> dict[str, Any]:
        kind = str(action.get("type", "")).strip().lower()
        if kind == "goto":
            url = str(action.get("url", "")).strip()
            if not url:
                raise ValueError("goto requires url")
            self.page.goto(url, wait_until="domcontentloaded")
        elif kind == "click_role":
            role = str(action.get("role", "")).strip()
            name = str(action.get("name", "")).strip()
            if not role or not name:
                raise ValueError("click_role requires role and name")
            self.page.get_by_role(role, name=name, exact=True).click()
        elif kind == "click_text":
            text = str(action.get("text", "")).strip()
            if not text:
                raise ValueError("click_text requires text")
            self.page.get_by_text(text, exact=True).click()
        elif kind == "fill":
            label = str(action.get("label", "")).strip()
            value = str(action.get("value", ""))
            if not label:
                raise ValueError("fill requires label")
            self.page.get_by_label(label, exact=True).fill(value)
        elif kind == "press":
            key = str(action.get("key", "")).strip()
            if not key:
                raise ValueError("press requires key")
            self.page.keyboard.press(key)
        elif kind == "screenshot":
            path = str(action.get("path", "data/browser-e2e.png"))
            self.page.screenshot(path=path, full_page=True)
        else:
            raise ValueError(f"unsupported browser action: {kind}")
        return self.observe()

    def verify(self, before: Any, after: Any, action: dict[str, Any]) -> bool:
        expected_url = str(action.get("expected_url", "")).strip()
        expected_text = str(action.get("expected_text", "")).strip()
        if expected_url and expected_url not in str(after.get("url", "")):
            return False
        if expected_text and expected_text.lower() not in str(after.get("text", "")).lower():
            return False
        if action.get("type") == "screenshot":
            return True
        return before != after or bool(expected_url or expected_text)


__all__ = ["PlaywrightComputerAdapter"]
