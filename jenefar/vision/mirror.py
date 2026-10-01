
from __future__ import annotations

import io
import threading
from dataclasses import dataclass

from PIL import Image


@dataclass
class MirrorState:
    active: bool = False
    query: str = ""
    bbox: tuple[int, int, int, int] | None = None
    title: str = "Desktop mirror"


class DesktopMirror:
    """Live cropped desktop window mirror for the avatar holographic display."""

    def __init__(self, desktop, screen_vision) -> None:
        self.desktop = desktop
        self.screen_vision = screen_vision
        self.state = MirrorState()
        self._lock = threading.Lock()

    def start(self, query: str) -> dict[str, object]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("A window or app query is required.")

        result = self.screen_vision.locate_window(query)
        bbox = tuple(int(value) for value in result["bbox"])
        label = str(result.get("label") or query)

        with self._lock:
            self.state = MirrorState(
                active=True,
                query=query,
                bbox=bbox,
                title=label,
            )

        return {
            "active": True,
            "query": query,
            "label": label,
            "bbox": list(bbox),
            "provider": result.get("provider", ""),
        }

    def stop(self) -> dict[str, object]:
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
