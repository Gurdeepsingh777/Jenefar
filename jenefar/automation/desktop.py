from __future__ import annotations

import io
import os
from pathlib import Path


class DesktopAutomation:
    """Desktop primitives plus screenshot frames for semantic vision control."""

    SAFE_KEYS = {
        "enter", "esc", "tab", "space", "backspace", "delete",
        "left", "right", "up", "down", "home", "end",
        "ctrl", "shift", "alt", "win",
        *{f"f{i}" for i in range(1, 13)},
    }
    SAFE_HOTKEY_KEYS = SAFE_KEYS | {
        "a", "c", "v", "x", "z", "y", "w", "t", "l", "r", "s", "f"
    }

    def __init__(self, screenshot_dir: str | os.PathLike[str] = "data/screenshots"):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def backend_status(self) -> dict[str, object]:
        status: dict[str, object] = {
            "python": os.sys.version.split()[0],
            "pyautogui": False,
            "display": os.getenv("DISPLAY", ""),
            "wayland_display": os.getenv("WAYLAND_DISPLAY", ""),
            "session_type": os.getenv("XDG_SESSION_TYPE", ""),
        }
        try:
            import pyautogui
            status["pyautogui"] = True
            try:
                size = pyautogui.size()
                status["screen"] = {"width": int(size.width), "height": int(size.height)}
            except Exception as exc:
                status["screen_error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            status["import_error"] = f"{type(exc).__name__}: {exc}"
        if not status["pyautogui"]:
            status["install_command"] = "python -m pip install -r requirements-desktop.txt"
        return status

    def _pyautogui(self):
        try:
            import pyautogui
        except Exception as exc:
            raise RuntimeError(
                "Desktop backend unavailable: pyautogui is not installed. "
                "Install it with: python -m pip install -r requirements-desktop.txt"
            ) from exc
        pyautogui.PAUSE = 0.05
        pyautogui.FAILSAFE = True
        return pyautogui

    def screen_size(self) -> dict[str, int]:
        size = self._pyautogui().size()
        return {"width": int(size.width), "height": int(size.height)}

    def _capture_screen_image(self):
        """Capture the full desktop without invoking PyAutoGUI screenshot helpers."""
        try:
            import mss
            from PIL import Image

            with mss.mss() as capture:
                monitor = capture.monitors[0]
                shot = capture.grab(monitor)
                return Image.frombytes("RGB", shot.size, shot.rgb)
        except Exception as exc:
            raise RuntimeError(
                "Desktop screenshot capture failed on the current Wayland/X11 session. "
                f"mss error: {type(exc).__name__}: {exc}"
            ) from exc

    def capture_frame(self, *, max_dimension: int = 1600, save: bool = False):
        from jenefar.vision.screen import ScreenFrame

        image = self._capture_screen_image()
        width, height = int(image.width), int(image.height)
        max_dimension = max(640, min(int(max_dimension), 2560))
        encoded = image
        longest = max(width, height)
        if longest > max_dimension:
            scale = max_dimension / float(longest)
            encoded = image.resize(
                (
                    max(1, int(round(width * scale))),
                    max(1, int(round(height * scale))),
                )
            )

        buffer = io.BytesIO()
        encoded.save(buffer, format="PNG")

        path = None
        if save:
            filename = self.screenshot_dir / "semantic_screen.png"
            image.save(filename)
            path = str(filename)

        return ScreenFrame(
            png_bytes=buffer.getvalue(),
            width=width,
            height=height,
            encoded_width=int(encoded.width),
            encoded_height=int(encoded.height),
            path=path,
        )

    def click(self, x: int, y: int, button: str = "left") -> dict[str, object]:
        if x < 0 or y < 0:
            raise ValueError("Coordinates must be non-negative.")
        if button not in {"left", "right", "middle"}:
            raise ValueError("Unsupported mouse button.")
        size = self._pyautogui().size()
        if x >= int(size.width) or y >= int(size.height):
            raise ValueError("Click coordinates are outside the current screen.")
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

    def hotkey(self, keys: list[str]) -> dict[str, object]:
        normalized = [str(key).strip().lower() for key in keys if str(key).strip()]
        if not normalized or len(normalized) > 4:
            raise ValueError("A hotkey must contain 1 to 4 keys.")
        if any(key not in self.SAFE_HOTKEY_KEYS for key in normalized):
            raise ValueError("Hotkey contains an unsupported key.")
        self._pyautogui().hotkey(*normalized)
        return {"action": "hotkey", "keys": normalized}

    def scroll(self, clicks: int) -> dict[str, object]:
        amount = max(-20, min(20, int(clicks)))
        if amount == 0:
            raise ValueError("Scroll amount cannot be zero.")
        self._pyautogui().scroll(amount)
        return {"action": "scroll", "clicks": amount}

    def screenshot(self, filename: str = "screen.png") -> dict[str, object]:
        clean = Path(filename).name
        path = self.screenshot_dir / clean
        self._pyautogui().screenshot(str(path))
        return {"action": "screenshot", "path": str(path)}
