from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from jenefar.avatar.controller import AvatarController
from jenefar.avatar.server import AvatarServer
from jenefar.production.readiness import check
from jenefar.browser.playwright_adapter import PlaywrightComputerAdapter


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_readiness_requires_remote_auth_and_tls(monkeypatch, tmp_path):
    monkeypatch.setenv("JENEFAR_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("JENEFAR_HOST", "0.0.0.0")
    monkeypatch.setenv("JENEFAR_AUTH_USER", "")
    monkeypatch.setenv("JENEFAR_AUTH_PASSWORD", "")
    monkeypatch.delenv("JENEFAR_TLS_CERT", raising=False)
    monkeypatch.delenv("JENEFAR_TLS_KEY", raising=False)
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "")
    result = check()
    assert result["ready"] is False
    assert any("remote deployment requires" in item for item in result["failures"])


def test_readiness_explicit_approval_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("JENEFAR_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("JENEFAR_REQUIRE_EXPLICIT_APPROVAL_SECRET", "1")
    monkeypatch.delenv("JENEFAR_APPROVAL_SECRET", raising=False)
    monkeypatch.setenv("JENEFAR_HOST", "127.0.0.1")
    result = check()
    assert any("JENEFAR_APPROVAL_SECRET" in item for item in result["failures"])


def test_readiness_loads_project_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JENEFAR_APPROVAL_SECRET=test-secret\n"
        "JENEFAR_REQUIRE_EXPLICIT_APPROVAL_SECRET=1\n"
        "JENEFAR_HOST=127.0.0.1\n"
        "JENEFAR_LOCAL_LLM_BASE_URL=http://127.0.0.1:9\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JENEFAR_ENV_FILE", str(env_file))
    monkeypatch.delenv("JENEFAR_APPROVAL_SECRET", raising=False)
    monkeypatch.setenv("JENEFAR_REQUIRE_EXPLICIT_APPROVAL_SECRET", "1")
    result = check()
    assert not any("approval secret" in item.lower() for item in result["warnings"])


def test_avatar_server_reuses_healthy_existing_instance():
    port = _free_port()
    first = AvatarServer(AvatarController(), port=port)
    second = None
    try:
        first.start()
        second = AvatarServer(AvatarController(), port=port)
        assert second.url == first.url
        second.start()
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(
            f"{first.url}health", timeout=1
        ) as response:
            assert response.status == 200
        second.stop()
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(
            f"{first.url}health", timeout=1
        ) as response:
            assert response.status == 200
    finally:
        if second is not None:
            second.stop()
        first.stop()


def test_avatar_server_rejects_unrelated_listener():
    port = _free_port()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(RuntimeError, match="already in use by another service"):
            AvatarServer(AvatarController(), port=port)
    finally:
        server.shutdown()
        server.server_close()


class FakeLocator:
    def __init__(self, text="hello"):
        self.text = text

    def inner_text(self, timeout=3000):
        return self.text


class FakePage:
    url = "http://example.test/"

    def title(self):
        return "Example"

    def locator(self, _selector):
        return FakeLocator()

    def goto(self, url, wait_until="domcontentloaded"):
        self.url = url

    def get_by_role(self, role, name, exact=True):
        return self

    def click(self):
        self.url = self.url + "#clicked"

    def get_by_text(self, text, exact=True):
        return self

    def get_by_label(self, label, exact=True):
        return self

    def fill(self, value):
        return None

    class keyboard:
        @staticmethod
        def press(key):
            return None

    def screenshot(self, path, full_page=True):
        Path(path).write_bytes(b"test")


def test_playwright_adapter_structured_actions(tmp_path):
    page = FakePage()
    adapter = PlaywrightComputerAdapter(page)
    before = adapter.observe()
    after = adapter.act({"type": "goto", "url": "http://example.test/new", "expected_url": "new"})
    assert adapter.verify(before, after, {"type": "goto", "expected_url": "new"})
    shot = tmp_path / "browser.png"
    result = adapter.act({"type": "screenshot", "path": str(shot)})
    assert shot.exists()
    assert adapter.verify(after, result, {"type": "screenshot"})
