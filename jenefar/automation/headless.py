from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jenefar.vision.screen import ScreenFrame


@dataclass
class VirtualElement:
    label: str
    role: str
    bbox: tuple[int, int, int, int]
    text: str = ""
    confidence: float = 0.99

    def as_dict(self) -> dict[str, Any]:
        x1, y1, x2, y2 = self.bbox
        return {
            "label": self.label,
            "role": self.role,
            "confidence": self.confidence,
            "bbox": [x1, y1, x2, y2],
            "text": self.text,
        }


class HeadlessDesktopAutomation:
    """Deterministic GUI simulator for safe CI/headless validation.

    It never imports pyautogui, never touches the real display, and never sends
    input to the host desktop. It exercises the same semantic locate/click/type
    path used by the live GUI agent.
    """

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self._width = int(width)
        self._height = int(height)
        self._focused: str | None = None
        self._typed_text = ""
        self._last_click: dict[str, Any] | None = None
        self._scroll = 0
        self._elements = self._default_elements()

    def _default_elements(self) -> dict[str, VirtualElement]:
        return {
            "search box": VirtualElement(
                "Search box",
                "textbox",
                (180, 110, 640, 165),
                "Search",
            ),
            "submit button": VirtualElement(
                "Submit button",
                "button",
                (700, 110, 860, 165),
                "Submit",
            ),
            "settings": VirtualElement(
                "Settings",
                "button",
                (1050, 40, 1180, 90),
                "Settings",
            ),
        }

    def screen_size(self) -> dict[str, int]:
        return {"width": self._width, "height": self._height}

    def capture_frame(self, *, max_dimension: int = 1600, save: bool = False) -> ScreenFrame:
        # A semantic fixture does not need a real screenshot. The empty byte
        # payload is intentionally non-rendered and is never sent to a model.
        return ScreenFrame(
            png_bytes=b"",
            width=self._width,
            height=self._height,
            encoded_width=self._width,
            encoded_height=self._height,
            path=None,
        )

    def semantic_elements(self, _task: str) -> list[dict[str, Any]]:
        items = [element.as_dict() for element in self._elements.values()]
        search = self._elements["search box"]
        if self._typed_text:
            search.text = self._typed_text
        return items

    def _element_at(self, x: int, y: int) -> VirtualElement | None:
        for element in self._elements.values():
            x1, y1, x2, y2 = element.bbox
            if x1 <= x <= x2 and y1 <= y <= y2:
                return element
        return None

    def click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        if not 0 <= int(x) < self._width or not 0 <= int(y) < self._height:
            raise ValueError("Virtual click is outside the simulated screen.")
        element = self._element_at(int(x), int(y))
        if element is not None:
            self._focused = element.label.lower()
        self._last_click = {
            "action": "click",
            "x": int(x),
            "y": int(y),
            "button": button,
            "target": element.label if element else None,
            "headless": True,
        }
        if element and element.label.lower() == "submit button":
            self._elements["submit button"].text = "Submitted"
        return dict(self._last_click)

    def type_text(self, text: str) -> dict[str, Any]:
        if len(text) > 4000:
            raise ValueError("Text input is limited to 4000 characters.")
        if self._focused != "search box":
            raise RuntimeError("No virtual text field is focused.")
        self._typed_text = str(text)
        return {
            "action": "type_text",
            "chars": len(str(text)),
            "text": str(text),
            "headless": True,
        }

    def press(self, key: str) -> dict[str, Any]:
        return {"action": "press", "key": str(key), "headless": True}

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        return {"action": "hotkey", "keys": [str(x) for x in keys], "headless": True}

    def scroll(self, clicks: int) -> dict[str, Any]:
        amount = max(-20, min(20, int(clicks)))
        if amount == 0:
            raise ValueError("Scroll amount cannot be zero.")
        self._scroll += amount
        return {
            "action": "scroll",
            "clicks": amount,
            "virtual_scroll": self._scroll,
            "headless": True,
        }

    def screenshot(self, filename: str = "screen.png") -> dict[str, Any]:
        # No physical screenshot is written in the safe backend.
        return {
            "action": "screenshot",
            "path": str(Path(filename).name),
            "headless": True,
            "written": False,
        }


__all__ = ["VirtualElement", "HeadlessDesktopAutomation"]
