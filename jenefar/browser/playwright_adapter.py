from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jenefar.security.policy import safe_path, validate_url


@dataclass
class PlaywrightComputerAdapter:
    """Real Chromium adapter for the ComputerAgent contract."""

    page: Any
    allowed_origins: tuple[str, ...] = ()
    allow_private_hosts: bool = False
    screenshot_root: str | Path = "data"

    def _navigation_target(self, raw_url: str) -> str:
        url = validate_url(raw_url, allow_private=self.allow_private_hosts)
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/")
        allowed = {
            str(item).strip().lower().rstrip("/")
            for item in self.allowed_origins
            if str(item).strip()
        }
        if allowed and origin not in allowed:
            raise PermissionError("browser navigation target is outside configured allowed origins")
        return url

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
            self.page.goto(self._navigation_target(url), wait_until="domcontentloaded")
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
            root = Path(self.screenshot_root).expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
            requested = str(action.get("path", root / "browser-e2e.png"))
            path = safe_path(requested, [root])
            path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path), full_page=True)
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
