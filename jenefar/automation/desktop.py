from __future__ import annotations

import os
from pathlib import Path


class DesktopAutomation:
    """Explicit, approval-gated desktop primitives."""

    SAFE_KEYS = {
        "enter", "esc", "tab", "space", "backspace", "delete",
        "left", "right", "up", "down", "home", "end",
        "ctrl", "shift", "alt", "win",
        *{f"f{i}" for i in range(1, 13)},
    }

    def __init__(self, screenshot_dir: str | os.PathLike[str] = "data/screenshots"):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def _pyautogui(self):
        try:
            import pyautogui
        except Exception as exc:
            raise RuntimeError(
                "Desktop automation requires optional dependency 'pyautogui'."
            ) from exc
        pyautogui.PAUSE = 0.05
        pyautogui.FAILSAFE = True
        return pyautogui

    def screen_size(self) -> dict[str, int]:
        size = self._pyautogui().size()
        return {"width": int(size.width), "height": int(size.height)}

    def click(self, x: int, y: int, button: str = "left") -> dict[str, object]:
        if x < 0 or y < 0:
            raise ValueError("Coordinates must be non-negative.")
        if button not in {"left", "right", "middle"}:
            raise ValueError("Unsupported mouse button.")
        self._pyautogui().click(x=int(x), y=int(y), button=button)
        return {"action": "click", "x": int(x), "y": int(y), "button": button}

    def type_text(self, text: str) -> dict[str, object]:
        if len(text) > 4000:
            raise ValueError("Text input is limited to 4000 characters.")
        self._pyautogui().write(text, interval=0.01)
        return {"action": "type_text", "chars": len(text)}

    def press(self, key: str) -> dict[str, object]:
        key = key.strip().lower()
        if key not in self.SAFE_KEYS:
            raise ValueError(f"Unsupported key: {key}")
        self._pyautogui().press(key)
        return {"action": "press", "key": key}

    def screenshot(self, filename: str = "screen.png") -> dict[str, object]:
        clean = Path(filename).name
        path = self.screenshot_dir / clean
        self._pyautogui().screenshot(str(path))
        return {"action": "screenshot", "path": str(path)}
