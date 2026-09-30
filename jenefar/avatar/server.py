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
    voice_handler = None

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(
            status,
            "application/json; charset=utf-8",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        return value if isinstance(value, dict) else {}

    def _serve_file(self, relative: str) -> None:
        root = ASSET_DIR.resolve()
        target = (ASSET_DIR / relative.lstrip("/")).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._send(403, "text/plain; charset=utf-8", b"Forbidden")
            return
        if not target.is_file():
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
            ".ico": "image/x-icon",
        }.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, content_type, target.read_bytes())

    def do_GET(self) -> None:
        path = urlparse(self.path).path or "/"
        try:
            if path == "/":
                self._serve_file("index.html")
                return
            if path == "/health":
                self._json(
                    200,
                    {
                        "status": "ok",
                        "avatar": self.controller.current(),
                        "vrm_available": bool(self.vrm_path and self.vrm_path.is_file()),
                    },
                )
                return
            if path == "/avatar.vrm":
                if not self.vrm_path or not self.vrm_path.is_file():
                    self._send(404, "text/plain; charset=utf-8", b"VRM unavailable")
                    return
                self._send(200, "model/gltf-binary", self.vrm_path.read_bytes())
                return
            if path == "/evaluation":
                html = render_dashboard(Path("data/evaluation.jsonl"))
                self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
                return
            if path.startswith("/avatar/"):
                self._serve_file(path[len("/avatar/"):])
                return
            self._serve_file(path.lstrip("/"))
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/voice/text":
                if self.voice_handler is None:
                    self._json(503, {"error": "Browser voice handler unavailable."})
                    return
                result = self.voice_handler(str(body.get("text", "")))
                self._json(200, result if isinstance(result, dict) else {"result": result})
                return
            if path == "/settings":
                value = UISettings(Path("data/ui_settings.json")).update(body)
                self._json(200, {"settings": value})
                return
            if path == "/approval/reject":
                pending_id = str(body.get("approve_id", "")).strip()
                if not self.tool_broker or not pending_id:
                    self._json(400, {"error": "approval id required"})
                    return
                self._json(200, {"result": self.tool_broker.reject(pending_id)})
                return
            if path == "/realtime/session":
                self._json(200, create_ephemeral_session(self.tool_broker))
                return
            if path == "/realtime/tool":
                pending_id = str(body.get("approve_id", "")).strip()
                if pending_id and self.tool_broker:
                    self._json(200, {"result": self.tool_broker.approve(pending_id)})
                    return
                tool_name = str(body.get("name", "")).strip()
                args = body.get("arguments", {})
                if not tool_name or not isinstance(args, dict):
                    self._json(400, {"error": "tool name and object arguments are required"})
                    return
                self._json(200, {"result": invoke_realtime_tool(tool_name, args)})
                return
            self._send(404, "text/plain; charset=utf-8", b"Not found")
        except RealtimeSessionError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *_args) -> None:
        return

class AvatarServer:
    """Local HTTP server for the Jenefar avatar workspace."""

    def __init__(
        self,
        controller: AvatarController,
        *,
        host: str = "127.0.0.1",
        port: int = 8787,
        vrm_path: Path | None = None,
        tool_broker=None,
        voice_handler=None,
    ) -> None:
        self.controller = controller
        self.host = host
        self.port = int(port)
        self.vrm_path = Path(vrm_path).expanduser().resolve() if vrm_path else None
        self.tool_broker = tool_broker
        self.voice_handler = voice_handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def _build_handler(self):
        controller = self.controller
        vrm_path = self.vrm_path
        tool_broker = self.tool_broker
        voice_handler = self.voice_handler

        class Handler(_AvatarHandler):
            pass

        Handler.controller = controller
        Handler.vrm_path = vrm_path
        Handler.tool_broker = tool_broker
        Handler.voice_handler = voice_handler
        return Handler

    def start(self) -> None:
        if self._server is not None:
            return
        handler = self._build_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="jenefar-avatar-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None


    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        self._send(
            status,
            "application/json; charset=utf-8",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"invalid JSON: {type(exc).__name__}: {exc}") from exc
        return value if isinstance(value, dict) else {}

    def _safe_asset(self, relative: str) -> Path | None:
        candidate = (ASSET_DIR / relative.lstrip("/")).resolve()
        try:
            candidate.relative_to(ASSET_DIR.resolve())
        except ValueError:
            return None
        if candidate.is_file():
            return candidate
        return None

    def _serve_file(self, relative: str) -> None:
        path = self._safe_asset(relative)
        if path is None:
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        suffix = path.suffix.lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
            ".ico": "image/x-icon",
        }
        self._send(200, types.get(suffix, "application/octet-stream"), path.read_bytes())

    def do_GET(self) -> None:
        path = urlparse(self.path).path or "/"
        try:
            if path == "/":
                self._serve_file("index.html")
                return
            if path == "/health":
                self._json(
                    200,
                    {
                        "status": "ok",
                        "avatar": self.controller.current(),
                        "vrm_available": bool(self.vrm_path and self.vrm_path.is_file()),
                    },
                )
                return
            if path == "/events":
                subscriber = self.controller.subscribe()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    while True:
                        event = subscriber.get()
                        payload = json.dumps(event, ensure_ascii=False)
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    self.controller.unsubscribe(subscriber)
                return
            if path == "/avatar.vrm":
                if not self.vrm_path or not self.vrm_path.is_file():
                    self._send(404, "text/plain; charset=utf-8", b"VRM unavailable")
                    return
                self._send(200, "model/gltf-binary", self.vrm_path.read_bytes())
                return
            if path == "/evaluation":
                html = render_dashboard(Path("data/evaluation.jsonl"))
                self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
                return
            if path.startswith("/avatar/"):
                self._serve_file(path[len("/avatar/"):])
                return
            self._serve_file(path.lstrip("/"))
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/voice/text":
                if self.voice_handler is None:
                    self._json(503, {"error": "Browser voice handler unavailable."})
                    return
                result = self.voice_handler(str(body.get("text", "")))
                self._json(200, result if isinstance(result, dict) else {"result": result})
                return
            if path == "/settings":
                settings = UISettings(Path("data/ui_settings.json"))
                value = settings.update(body)
                self._json(200, {"settings": value})
                return
            if path == "/approval/reject":
                pending_id = str(body.get("approve_id", "")).strip()
                if not self.tool_broker or not pending_id:
                    self._json(400, {"error": "approval id required"})
                    return
                result = self.tool_broker.reject(pending_id)
                self._json(200, {"result": result})
                return
            if path == "/realtime/session":
                result = create_ephemeral_session(self.tool_broker)
                self._json(200, result)
                return
            if path == "/realtime/tool":
                pending_id = str(body.get("approve_id", "")).strip()
                if pending_id and self.tool_broker:
                    result = self.tool_broker.approve(pending_id)
                    self._json(200, {"result": result})
                    return
                tool_name = str(body.get("name", "")).strip()
                args = body.get("arguments", {})
                if not tool_name or not isinstance(args, dict):
                    self._json(400, {"error": "tool name and object arguments are required"})
                    return
                result = invoke_realtime_tool(tool_name, args)
                self._json(200, {"result": result})
                return
            self._send(404, "text/plain; charset=utf-8", b"Not found")
        except RealtimeSessionError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
