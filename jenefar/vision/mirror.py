
from __future__ import annotations

import io
import threading
from dataclasses import dataclass

from PIL import Image

from jenefar.automation.window_control import DesktopWindowControl


@dataclass
class MirrorState:
    active: bool = False
    query: str = ""
    bbox: tuple[int, int, int, int] | None = None
    title: str = "Desktop mirror"
    window_id: str = ""
    control_backend: str = "none"
    capture_mode: str = "screen_crop"
    native_hidden: bool = False


class DesktopMirror:
    """Live cropped desktop window mirror for the avatar holographic display."""

    def __init__(self, desktop, screen_vision, window_control=None) -> None:
        self.desktop = desktop
        self.screen_vision = screen_vision
        self.window_control = window_control or DesktopWindowControl()
        self.state = MirrorState()
        self._lock = threading.Lock()

    def start(self, query: str) -> dict[str, object]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("A window or app query is required.")

        native = None
        try:
            native = self.window_control.find(query)
        except Exception:
            native = None

        backend = self.window_control.backend
        if native and backend in {"wmctrl", "xdotool"}:
            bbox = (native.x, native.y, native.x + native.width, native.y + native.height)
            label = native.title or query
            provider = "native_window"
            capture_mode = "native_window"
        else:
            if not self.desktop.screen_capture_enabled():
                raise PermissionError(
                    "Desktop mirror cannot fall back to full-screen capture. "
                    "Use a supported native window backend (wmctrl/xdotool), "
                    "or explicitly enable JENEFAR_ALLOW_SCREEN_CAPTURE=1."
                )
            result = self.screen_vision.locate_window(query)
            bbox = tuple(int(value) for value in result["bbox"])
            label = str(result.get("label") or query)
            provider = result.get("provider", "")
            capture_mode = "screen_crop"
        window_id = native.window_id if native else ""

        with self._lock:
            self.state = MirrorState(
                active=True,
                query=query,
                bbox=bbox,
                title=label,
                window_id=window_id,
                control_backend=backend,
                capture_mode=capture_mode,
                native_hidden=False,
            )

        return {
            "active": True,
            "query": query,
            "label": label,
            "bbox": list(bbox),
            "window_id": window_id,
            "control_backend": backend,
            "capture_mode": capture_mode,
            "native_control_available": bool(native and backend != "none"),
            "provider": provider,
        }

    def stop(self) -> dict[str, object]:
        previous = self.status()
        if previous.get("native_hidden") and previous.get("query"):
            try:
                self.restore_native(str(previous["query"]))
            except Exception:
                pass
        with self._lock:
            self.state = MirrorState()
        return {"active": False}

    def status(self) -> dict[str, object]:
        with self._lock:
            state = self.state
            return {
                "active": state.active,
                "query": state.query,
                "bbox": list(state.bbox) if state.bbox else None,
                "title": state.title,
                "window_id": state.window_id,
                "control_backend": state.control_backend,
                "capture_mode": state.capture_mode,
                "native_hidden": state.native_hidden,
            }

    def frame(self) -> bytes | None:
        with self._lock:
            state = MirrorState(
                active=self.state.active,
                query=self.state.query,
                bbox=self.state.bbox,
                title=self.state.title,
            )

        if not state.active or not state.bbox:
            return None

        if state.window_id and state.control_backend in {"wmctrl", "xdotool"}:
            try:
                direct = self.window_control.capture(
                    self.window_control.find(state.query)
                )
                image = Image.open(io.BytesIO(direct)).convert("RGB")
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=88, optimize=True)
                return buffer.getvalue()
            except Exception:
                pass

        frame = self.desktop.capture_frame(max_dimension=1600, save=False)
        image = Image.open(io.BytesIO(frame.png_bytes)).convert("RGB")

        scale_x = frame.encoded_width / float(frame.width)
        scale_y = frame.encoded_height / float(frame.height)
        x1, y1, x2, y2 = state.bbox
        encoded_bbox = (
            max(0, int(round(x1 * scale_x))),
            max(0, int(round(y1 * scale_y))),
            min(image.width, int(round(x2 * scale_x))),
            min(image.height, int(round(y2 * scale_y))),
        )

        if encoded_bbox[2] <= encoded_bbox[0] or encoded_bbox[3] <= encoded_bbox[1]:
            return None

        cropped = image.crop(encoded_bbox)
        buffer = io.BytesIO()
        cropped.save(buffer, format="JPEG", quality=84, optimize=True)
        return buffer.getvalue()


    def transfer(self, query: str, *, hide_native: bool = True) -> dict[str, object]:
        started = self.start(query)
        if not hide_native:
            return {**started, "native_hidden": False, "transfer_mode": "mirror_only"}

        if (
            not started.get("window_id")
            or started.get("control_backend") not in {"wmctrl", "xdotool"}
        ):
            return {
                **started,
                "native_hidden": False,
                "transfer_mode": "mirror_only",
                "warning": (
                    "Direct native-window capture/control is not available for this window. "
                    "The live mirror is active, but the native window remains visible."
                ),
            }

        window = self.window_control.find(query)
        host_titles = ("jenefar avatar", "jenefar ai")
        if any(marker in window.title.lower() for marker in host_titles):
            return {
                **started,
                "native_hidden": False,
                "transfer_mode": "mirror_only",
                "warning": "The Jenefar host window stays visible so the controller remains reachable.",
            }
        self.window_control.hide(window)
        with self._lock:
            self.state.native_hidden = True
            self.state.capture_mode = "native_window"
        return {
            **self.status(),
            "transfer_mode": "live_native_window",
            "native_hidden": True,
        }

    def restore_native(self, query: str | None = None) -> dict[str, object]:
        selected = str(query or "").strip() or str(self.status().get("query", ""))
        if not selected:
            raise ValueError("A window name is required to restore.")
        window = self.window_control.find(selected)
        result = self.window_control.restore(window)
        with self._lock:
            self.state.native_hidden = False
        return {**self.status(), **result}

    def focus_native(self, query: str) -> dict[str, object]:
        window = self.window_control.find(query)
        return self.window_control.activate(window)
