
from __future__ import annotations

import io
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class WindowInfo:
    window_id: str
    x: int
    y: int
    width: int
    height: int
    title: str
    desktop: str = ""


class DesktopWindowControl:
    """Best-effort native window control and direct X11/XWayland window capture."""

    def __init__(self) -> None:
        self.session_type = os.getenv("XDG_SESSION_TYPE", "").strip().lower()
        self.display = os.getenv("DISPLAY", "").strip()
        self._backend = self._detect_backend()

    @staticmethod
    def _which(*commands: str) -> str | None:
        for command in commands:
            found = shutil.which(command)
            if found:
                return found
        return None

    def _detect_backend(self) -> str:
        if self.display and self._which("wmctrl"):
            return "wmctrl"
        if self.display and self._which("xdotool"):
            return "xdotool"
        if os.getenv("HYPRLAND_INSTANCE_SIGNATURE") and self._which("hyprctl"):
            return "hyprland"
        if os.getenv("SWAYSOCK") and self._which("swaymsg"):
            return "sway"
        return "none"

    @property
    def backend(self) -> str:
        return self._backend

    def status(self) -> dict[str, object]:
        return {
            "backend": self._backend,
            "session_type": self.session_type,
            "display": bool(self.display),
            "direct_capture": bool(
                self._backend in {"wmctrl", "xdotool"}
                and self._which("ffmpeg", "import")
            ),
            "control": self._backend != "none",
        }

    def list_windows(self) -> list[WindowInfo]:
        if self._backend == "wmctrl":
            return self._list_wmctrl()
        if self._backend == "xdotool":
            return self._list_xdotool()
        if self._backend == "hyprland":
            return self._list_hyprland()
        if self._backend == "sway":
            return self._list_sway()
        return []

    def find(self, query: str) -> WindowInfo:
        lowered = str(query or "").strip().lower()
        if not lowered:
            raise ValueError("A window or application name is required.")

        windows = self.list_windows()
        ranked = []
        for window in windows:
            title = window.title.lower()
            exact = 0 if lowered == title else 1
            contains = 0 if lowered in title else 1
            ranked.append((exact, contains, -window.width * window.height, window))

        matches = [item for item in ranked if item[1] == 0]
        if not matches:
            raise LookupError(
                f"No controllable native window matched '{query}'. "
                f"Window-control backend: {self._backend}"
            )
        matches.sort(key=lambda item: item[:3])
        return matches[0][3]

    def activate(self, window: WindowInfo) -> dict[str, object]:
        if self._backend == "wmctrl":
            self._run(["wmctrl", "-ia", window.window_id])
        elif self._backend == "xdotool":
            self._run(["xdotool", "windowactivate", window.window_id])
        elif self._backend == "hyprland":
            self._run(["hyprctl", "dispatch", "focuswindow", f"address:{window.window_id}"])
        elif self._backend == "sway":
            self._run(["swaymsg", f'[con_id="{window.window_id}"] focus'])
        else:
            raise RuntimeError("No supported native window-control backend is available.")
        return {"ok": True, "operation": "focus", "window_id": window.window_id, "title": window.title}

    def hide(self, window: WindowInfo) -> dict[str, object]:
        if self._backend == "wmctrl":
            self._run(["wmctrl", "-ir", window.window_id, "-b", "add,hidden"])
        elif self._backend == "xdotool":
            self._run(["xdotool", "windowminimize", window.window_id])
        elif self._backend == "hyprland":
            self._run(["hyprctl", "dispatch", "movetoworkspacesilent", "special:minimized", f"address:{window.window_id}"])
        elif self._backend == "sway":
            self._run(["swaymsg", f'[con_id="{window.window_id}"] move scratchpad'])
        else:
            raise RuntimeError("Native hide is not available for the current windowing backend.")
        return {"ok": True, "operation": "hide", "window_id": window.window_id, "title": window.title}

    def restore(self, window: WindowInfo) -> dict[str, object]:
        if self._backend == "wmctrl":
            self._run(["wmctrl", "-ir", window.window_id, "-b", "remove,hidden"])
            self._run(["wmctrl", "-ia", window.window_id])
        elif self._backend == "xdotool":
            self._run(["xdotool", "windowmap", window.window_id])
            self._run(["xdotool", "windowactivate", window.window_id])
        elif self._backend == "hyprland":
            self._run(["hyprctl", "dispatch", "togglespecialworkspace", "minimized"])
            self._run(["hyprctl", "dispatch", "focuswindow", f"address:{window.window_id}"])
        elif self._backend == "sway":
            self._run(["swaymsg", f'[con_id="{window.window_id}"] scratchpad show'])
            self._run(["swaymsg", f'[con_id="{window.window_id}"] focus'])
        else:
            raise RuntimeError("Native restore is not available for the current windowing backend.")
        return {"ok": True, "operation": "restore", "window_id": window.window_id, "title": window.title}

    def capture(self, window: WindowInfo) -> bytes:
        if self._backend not in {"wmctrl", "xdotool"}:
            raise RuntimeError(
                "Direct native-window capture is unavailable. "
                "The current window-control backend is not X11/XWayland."
            )

        ffmpeg = self._which("ffmpeg")
        if ffmpeg:
            completed = subprocess.run(
                [
                    ffmpeg,
                    "-loglevel", "error",
                    "-f", "x11grab",
                    "-window_id", window.window_id,
                    "-frames:v", "1",
                    "-f", "image2pipe",
                    "-vcodec", "png",
                    "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout:
                return completed.stdout

        imagemagick = self._which("import")
        if imagemagick:
            completed = subprocess.run(
                [imagemagick, "-window", window.window_id, "png:-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout:
                return completed.stdout

        raise RuntimeError(
            "No working X11 window-capture utility is installed. "
            "Install ffmpeg or ImageMagick for direct window mirroring."
        )

    @staticmethod
    def _run(command: list[str]) -> str:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(
                f"{' '.join(command)} failed with exit code {completed.returncode}: {detail}"
            )
        return completed.stdout.strip()

    def _list_wmctrl(self) -> list[WindowInfo]:
        raw = self._run(["wmctrl", "-lG"])
        windows: list[WindowInfo] = []
        for line in raw.splitlines():
            parts = line.split(None, 7)
            if len(parts) < 8:
                continue
            try:
                windows.append(
                    WindowInfo(
                        window_id=parts[0],
                        x=int(parts[2]),
                        y=int(parts[3]),
                        width=int(parts[4]),
                        height=int(parts[5]),
                        desktop=parts[1],
                        title=parts[7].strip(),
                    )
                )
            except ValueError:
                continue
        return windows

    def _list_xdotool(self) -> list[WindowInfo]:
        raw = self._run(["xdotool", "search", "--onlyvisible", "--name", ".*"])
        windows: list[WindowInfo] = []
        for window_id in raw.splitlines():
            wid = window_id.strip()
            if not wid:
                continue
            try:
                title = self._run(["xdotool", "getwindowname", wid])
                geometry = self._run(["xdotool", "getwindowgeometry", wid])
                values: dict[str, int] = {}
                for line in geometry.splitlines():
                    line = line.strip()
                    if line.startswith("Position:"):
                        position = line.split(":", 1)[1].strip().split()[0]
                        x, y = position.split(",")
                        values["x"], values["y"] = int(x), int(y)
                    elif line.startswith("Geometry:"):
                        size = line.split(":", 1)[1].strip()
                        width, height = size.split("x")
                        values["width"], values["height"] = int(width), int(height)
                windows.append(
                    WindowInfo(
                        window_id=wid,
                        x=values.get("x", 0),
                        y=values.get("y", 0),
                        width=values.get("width", 0),
                        height=values.get("height", 0),
                        title=title.strip(),
                    )
                )
            except Exception:
                continue
        return windows

    def _list_hyprland(self) -> list[WindowInfo]:
        import json

        raw = self._run(["hyprctl", "-j", "clients"])
        clients = json.loads(raw)
        return [
            WindowInfo(
                window_id=str(item.get("address") or ""),
                x=int(item.get("at", [0, 0])[0]),
                y=int(item.get("at", [0, 0])[1]),
                width=int(item.get("size", [0, 0])[0]),
                height=int(item.get("size", [0, 0])[1]),
                title=str(item.get("title") or item.get("class") or ""),
            )
            for item in clients
            if item.get("address")
        ]

    def _list_sway(self) -> list[WindowInfo]:
        import json

        raw = self._run(["swaymsg", "-t", "get_tree"])
        tree = json.loads(raw)
        windows: list[WindowInfo] = []

        def walk(node: dict[str, Any]) -> None:
            rect = node.get("rect") or {}
            title = str(node.get("name") or node.get("app_id") or "")
            if node.get("type") == "con" and title:
                windows.append(
                    WindowInfo(
                        window_id=str(node.get("id") or ""),
                        x=int(rect.get("x", 0)),
                        y=int(rect.get("y", 0)),
                        width=int(rect.get("width", 0)),
                        height=int(rect.get("height", 0)),
                        title=title,
                    )
                )
            for child in node.get("nodes") or []:
                if isinstance(child, dict):
                    walk(child)
            for child in node.get("floating_nodes") or []:
                if isinstance(child, dict):
                    walk(child)

        walk(tree)
        return windows
