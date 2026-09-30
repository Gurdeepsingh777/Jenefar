from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from jenefar.avatar.controller import AvatarController
from jenefar.avatar.settings import UISettings
from jenefar.evaluation.dashboard import render_dashboard
from jenefar.realtime.server import (
    RealtimeSessionError,
    create_ephemeral_session,
    invoke_realtime_tool,
)


ASSET_DIR = Path(__file__).with_name("web")


class _AvatarHandler(BaseHTTPRequestHandler):
    controller: AvatarController
    vrm_path: Path | None
    tool_broker = None

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/events":
            self._events()
            return

        if path == "/avatar.vrm":
            self._vrm()
            return

        if path == "/avatar-photo.svg":
            body = self._photo_avatar_svg()
            self._send(200, "image/svg+xml; charset=utf-8", body.encode("utf-8"))
            return

        if path == "/settings":
            self._send(
                200,
                "application/json; charset=utf-8",
                json.dumps(UISettings().load()).encode("utf-8"),
            )
            return

        if path == "/health":
            payload = {
                "status": "ok",
                "avatar": self.controller.current(),
                "vrm_available": bool(self.vrm_path and self.vrm_path.is_file()),
            }
            self._send(
                200,
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            return

        if path == "/evaluation":
            self._send(200, "text/html; charset=utf-8", render_dashboard().encode("utf-8"))
            return

        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/vrm.js": ("vrm.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
            "/realtime.js": ("realtime.js", "text/javascript; charset=utf-8"),
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

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/realtime/tool":
            self._realtime_tool()
            return
        if path == "/settings":
            self._settings_update()
            return
        if path != "/realtime/session":
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        try:
            result = create_ephemeral_session(self.tool_broker)
        except RealtimeSessionError as exc:
            self._send(
                503,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
            return
        self._send(
            200,
            "application/json; charset=utf-8",
            json.dumps(result).encode("utf-8"),
        )

    def _settings_update(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = UISettings().update(payload)
        except Exception as exc:
            self._send(
                400,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
            return
        self._send(
            200,
            "application/json; charset=utf-8",
            json.dumps(result).encode("utf-8"),
        )

    def _realtime_tool(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            name = str(payload.get("name", ""))
            arguments = payload.get("arguments") or {}
            if payload.get("approve_id"):
                broker = self.tool_broker or None
                if broker is None:
                    raise RealtimeSessionError("Realtime broker is unavailable.")
                result = broker.approve(str(payload["approve_id"]))
            else:
                broker = self.tool_broker
                if broker is not None:
                    result = broker.invoke(name, arguments)
                else:
                    result = invoke_realtime_tool(name, arguments)
        except Exception as exc:
            self._send(
                400,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
            return

        parsed = json.loads(result)
        self._send(
            200,
            "application/json; charset=utf-8",
            json.dumps({"result": parsed}).encode("utf-8"),
        )

    @staticmethod
    def _photo_avatar_svg() -> str:
        return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 800">
  <defs>
    <radialGradient id="bg" cx="50%" cy="34%" r="72%">
      <stop offset="0%" stop-color="#253044"/>
      <stop offset="55%" stop-color="#0b0f18"/>
      <stop offset="100%" stop-color="#03050a"/>
    </radialGradient>
    <radialGradient id="skin" cx="48%" cy="35%" r="62%">
      <stop offset="0%" stop-color="#f5d9d0"/>
      <stop offset="100%" stop-color="#9e6f72"/>
    </radialGradient>
    <linearGradient id="hair" x1="0" x2="1">
      <stop offset="0%" stop-color="#05060a"/>
      <stop offset="50%" stop-color="#201d2c"/>
      <stop offset="100%" stop-color="#07080d"/>
    </linearGradient>
    <linearGradient id="dress" x1="0" x2="1">
      <stop offset="0%" stop-color="#0c1420"/>
      <stop offset="50%" stop-color="#1c2636"/>
      <stop offset="100%" stop-color="#0a111b"/>
    </linearGradient>
    <filter id="shadow"><feGaussianBlur stdDeviation="16"/></filter>
    <filter id="soft"><feGaussianBlur stdDeviation="4"/></filter>
  </defs>
  <rect width="640" height="800" rx="48" fill="url(#bg)"/>
  <ellipse cx="320" cy="740" rx="230" ry="38" fill="#000" opacity=".5" filter="url(#shadow)"/>
  <ellipse cx="320" cy="386" rx="165" ry="220" fill="#000" opacity=".3" filter="url(#soft)"/>
  <path d="M155 396c-35-185 55-310 165-311 125-1 213 129 165 311l-46-38c-12-130-64-186-131-186s-114 48-132 186z" fill="url(#hair)"/>
  <ellipse cx="320" cy="360" rx="126" ry="155" fill="url(#skin)"/>
  <path d="M196 300c7-95 59-153 124-153 74 0 119 74 124 154-38-36-81-54-124-54-43 0-84 18-124 53z" fill="url(#hair)" opacity=".94"/>
  <path d="M238 355c20-15 43-17 64-8M338 347c21-9 44-7 64 8" fill="none" stroke="#4f3940" stroke-width="9" stroke-linecap="round"/>
  <ellipse cx="273" cy="375" rx="16" ry="10" fill="#f7fbff"/><ellipse cx="367" cy="375" rx="16" ry="10" fill="#f7fbff"/>
  <circle cx="273" cy="376" r="5" fill="#67dfff"/><circle cx="367" cy="376" r="5" fill="#67dfff"/>
  <path d="M317 376c-2 23-8 37-18 50 11 7 23 8 39 2" fill="none" stroke="#9a6d70" stroke-width="4" stroke-linecap="round"/>
  <path d="M278 463c27 20 58 20 85 0-9 35-73 40-85 0z" fill="#7f3e55"/>
  <path d="M238 498v80h164v-80" fill="url(#skin)"/>
  <path d="M235 535c-87 14-142 79-166 192h502c-24-113-79-178-166-192l-85 82z" fill="url(#dress)"/>
  <path d="M231 539l89 83 89-83 31 54-120 115-120-115z" fill="#16263a" stroke="#61dfff" stroke-width="5" opacity=".9"/>
  <path d="M320 590l33 34-33 66-33-66z" fill="#9a7cff" opacity=".7" filter="url(#soft)"/>
  <circle cx="320" cy="625" r="8" fill="#e7fbff"/>
</svg>"""
    def _vrm(self) -> None:
        if not self.vrm_path or not self.vrm_path.is_file():
            self._send(404, "text/plain; charset=utf-8", b"No VRM model configured")
            return
        try:
            body = self.vrm_path.read_bytes()
        except OSError:
            self._send(500, "text/plain; charset=utf-8", b"VRM model unavailable")
            return
        self._send(200, "model/gltf-binary", body)

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
        vrm_path: str | Path | None = None,
        tool_broker=None,
    ):
        self.controller = controller
        self.tool_broker = tool_broker
        self.host = host
        self.port = port
        configured = vrm_path or os.getenv("JENEFAR_AVATAR_VRM_PATH", "")
        if configured:
            self.vrm_path = Path(configured).expanduser()
        else:
            bundled_sample = Path("data/avatar/AvatarSample_A_1.0.vrm.glb")
            self.vrm_path = bundled_sample if bundled_sample.is_file() else None
        if self.vrm_path and not self.vrm_path.is_absolute():
            self.vrm_path = (Path.cwd() / self.vrm_path).resolve()

        self._server = ThreadingHTTPServer((host, port), _AvatarHandler)
        self.host, self.port = self._server.server_address[0], self._server.server_address[1]
        self._server.RequestHandlerClass.controller = controller
        self._server.RequestHandlerClass.vrm_path = self.vrm_path
        self._server.RequestHandlerClass.tool_broker = tool_broker
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
