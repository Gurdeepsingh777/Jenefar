from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from jenefar.avatar.controller import AvatarController


ASSET_DIR = Path(__file__).with_name("web")


class _AvatarHandler(BaseHTTPRequestHandler):
    controller: AvatarController

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/events":
            self._events()
            return

        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
        }
        asset = assets.get(path)
        if not asset:
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return

        file_path = ASSET_DIR / asset[0]
        try:
            body = file_path.read_bytes()
        except OSError:
            self._send(500, "text/plain; charset=utf-8", b"Avatar asset unavailable")
            return
        self._send(200, asset[1], body)

    def _events(self) -> None:
        subscriber = self.controller.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            while True:
                try:
                    event = subscriber.get(timeout=25)
                    payload = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    try:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                    except Exception:
                        break
        finally:
            self.controller.unsubscribe(subscriber)

    def log_message(self, _format: str, *_args) -> None:
        return


class AvatarServer:
    def __init__(
        self,
        controller: AvatarController,
        host: str = "127.0.0.1",
        port: int = 8787,
    ):
        self.controller = controller
        self.host = host
        self.port = port
        self._server = ThreadingHTTPServer((host, port), _AvatarHandler)
        self._server.RequestHandlerClass.controller = controller
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="jenefar-avatar-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def serve_forever(self) -> None:
        try:
            self._server.serve_forever()
        finally:
            self._server.server_close()
