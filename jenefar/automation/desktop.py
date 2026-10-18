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
        """Diagnose actual display/input availability without saving a screenshot."""
        session_type = os.getenv("XDG_SESSION_TYPE", "").strip().lower()
        display = os.getenv("DISPLAY", "").strip()
        wayland_display = os.getenv("WAYLAND_DISPLAY", "").strip()
        status: dict[str, object] = {
            "python": os.sys.version.split()[0],
            "backend": "native",
            "session_type": session_type or "unknown",
            "display": display,
            "wayland_display": wayland_display,
            "pyautogui_imported": False,
            "pyautogui": False,
            "input_control": False,
            "screenshot_capture": False,
            "desktop_ready": False,
            "diagnosis": "",
            "recommendations": [],
        }
        recommendations: list[str] = []

        try:
            import pyautogui

            status["pyautogui_imported"] = True
            try:
                size = pyautogui.size()
                width, height = int(size.width), int(size.height)
                if width > 0 and height > 0:
                    status["screen"] = {"width": width, "height": height}
                    status["pyautogui"] = True
                    status["input_control"] = True
                else:
                    status["screen_error"] = f"Display returned invalid dimensions: {width}x{height}"
            except Exception as exc:
                status["screen_error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            status["import_error"] = f"{type(exc).__name__}: {exc}"
            recommendations.append(
                "Install desktop dependencies in the active venv: "
                "python -m pip install -r requirements-desktop.txt"
            )

        # Probe that an actual screen-capture session can be opened and has a
        # valid monitor geometry. This does not capture, save, or inspect pixels.
        try:
            import mss

            with mss.mss() as capture:
                monitors = list(capture.monitors or [])
                visible_monitors = [
                    monitor for monitor in monitors[1:]
                    if int(monitor.get("width", 0)) > 0 and int(monitor.get("height", 0)) > 0
                ]
                status["monitor_count"] = len(visible_monitors)
                if visible_monitors:
                    primary = visible_monitors[0]
                    status["capture_screen"] = {
                        "width": int(primary["width"]),
                        "height": int(primary["height"]),
                    }
                    status["screenshot_capture"] = True
                else:
                    status["screenshot_capture"] = False
                    status["screenshot_error"] = "No accessible monitor geometry was reported by MSS."
        except Exception as exc:
            status["screenshot_capture"] = False
            status["screenshot_error"] = f"{type(exc).__name__}: {exc}"
            recommendations.append(
                "Check screenshot dependencies and desktop/session permissions. "
                "Install with: python -m pip install -r requirements-desktop.txt"
            )

        if not status["input_control"]:
            if session_type == "wayland" and not display:
                diagnosis = (
                    "Wayland session detected, but DISPLAY is unset and PyAutoGUI cannot access an X11/XWayland display. "
                    "Native mouse/keyboard control is unavailable; screenshot capture is reported separately."
                )
                recommendations.append(
                    "For PyAutoGUI input control, log into an X11 session or verify that XWayland is enabled and DISPLAY is set. "
                    "Do not manually invent DISPLAY values; use the value supplied by your desktop session."
                )
            elif session_type == "wayland":
                diagnosis = (
                    "Wayland session detected, but PyAutoGUI could not verify usable screen geometry. "
                    "The XWayland/display connection or desktop permissions may be unavailable."
                )
                recommendations.append(
                    "Check that the current desktop session owns the DISPLAY socket and that XWayland is running; "
                    "re-run python run.py --doctor from that same desktop session."
                )
            elif not status["pyautogui_imported"]:
                diagnosis = "PyAutoGUI could not be imported, so native input control is unavailable."
            else:
                diagnosis = "PyAutoGUI imported, but it could not verify a usable display for input control."
                recommendations.append(
                    "Run Jenefar from a logged-in graphical desktop session; headless terminals and SSH sessions may not expose a display."
                )
        elif status["screenshot_capture"]:
            diagnosis = "Native input control and screen-capture display access are available."
        else:
            diagnosis = (
                "Mouse/keyboard control appears available, but MSS could not open a usable monitor for screen capture."
            )

        status["diagnosis"] = diagnosis
        status["recommendations"] = recommendations
        status["desktop_ready"] = bool(status["input_control"] and status["screenshot_capture"])
        if not status["pyautogui_imported"] or not status["screenshot_capture"]:
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
