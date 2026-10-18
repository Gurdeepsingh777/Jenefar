from __future__ import annotations

import sys
from types import SimpleNamespace

from jenefar.automation.desktop import DesktopAutomation
from jenefar.automation.headless import HeadlessDesktopAutomation


def test_wayland_backend_reports_input_and_capture_separately(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", "")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    def fail_size():
        raise RuntimeError("cannot connect to X display")

    class FakeMSS:
        def __enter__(self):
            self.monitors = [
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ]
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(size=fail_size))
    monkeypatch.setitem(sys.modules, "mss", SimpleNamespace(mss=FakeMSS))

    status = DesktopAutomation(tmp_path / "screenshots").backend_status()

    assert status["pyautogui_imported"] is True
    assert status["input_control"] is False
    assert status["screenshot_capture"] is True
    assert status["desktop_ready"] is False
    assert status["session_type"] == "wayland"
    assert "Wayland session detected" in status["diagnosis"]
    assert status["recommendations"]


def test_desktop_backend_status_reports_capture_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setenv("WAYLAND_DISPLAY", "")

    class FakeSize:
        width = 1366
        height = 768

    class FakeMSS:
        def __enter__(self):
            raise RuntimeError("X server refused connection")

        def __exit__(self, *_args):
            return False

    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(size=lambda: FakeSize()))
    monkeypatch.setitem(sys.modules, "mss", SimpleNamespace(mss=FakeMSS))

    status = DesktopAutomation(tmp_path / "screenshots").backend_status()

    assert status["input_control"] is True
    assert status["screenshot_capture"] is False
    assert status["desktop_ready"] is False
    assert "screen capture" in status["diagnosis"].lower()


def test_headless_backend_explicitly_reports_simulation_only():
    status = HeadlessDesktopAutomation(width=800, height=600).backend_status()

    assert status["backend"] == "headless_simulation"
    assert status["input_control"] is False
    assert status["screenshot_capture"] is False
    assert status["simulated_screen"] == {"width": 800, "height": 600}
    assert "does not control or capture" in status["diagnosis"]
