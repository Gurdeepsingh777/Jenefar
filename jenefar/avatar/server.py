from __future__ import annotations

import base64
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
    runtime_status = None
    cancel_active_task = None
    runtime_tasks = None
    auth_user = ""
    auth_password = ""

    def _authorized(self) -> bool:
        if not self.auth_user:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            user, password = decoded.split(":", 1)
        except Exception:
            return False
        return user == self.auth_user and password == self.auth_password

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Jenefar"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

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
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        return value if isinstance(value, dict) else {}

    def _asset(self, relative: str) -> Path | None:
        root = ASSET_DIR.resolve()
        candidate = (ASSET_DIR / relative.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def _serve_file(self, relative: str) -> None:
        target = self._asset(relative)
        if target is None:
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
            if path != "/health" and not self._require_auth():
                return
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
            if path == "/desktop/mirror/status":
                mirror = self.tool_broker
                payload = (
                    mirror.desktop_mirror_status()
                    if mirror and hasattr(mirror, "desktop_mirror_status")
                    else {"active": False}
                )
                self._json(200, payload)
                return
            if path == "/desktop/mirror.jpg":
                mirror = self.tool_broker
                frame = (
                    mirror.desktop_mirror_frame()
                    if mirror and hasattr(mirror, "desktop_mirror_frame")
                    else None
                )
                if not frame:
                    self._send(204, "image/jpeg", b"")
                    return
                self._send(200, "image/jpeg", frame)
                return
            if path == "/runtime/status":
                provider = self.runtime_status
                payload = provider() if callable(provider) else {"error": "runtime status unavailable"}
                self._json(200, payload if isinstance(payload, dict) else {"runtime": payload})
                return
            if path == "/runtime/metrics":
                provider = self.runtime_status
                payload = provider() if callable(provider) else {}
                production = payload.get("production", {}) if isinstance(payload, dict) else {}
                self._json(200, production.get("metrics", {}))
                return
            if path == "/production/readiness":
                provider = self.runtime_status
                payload = provider() if callable(provider) else {}
                production = payload.get("production", {}) if isinstance(payload, dict) else {}
                self._json(200, production.get("readiness", {"ready": False}))
                return
            if path == "/runtime/tasks":
                provider = self.runtime_tasks
                if not callable(provider):
                    self._json(503, {"error": "runtime task history unavailable"})
                    return
                query = parse_qs(urlparse(self.path).query)
                def first(name: str) -> str:
                    values = query.get(name, [""])
                    return str(values[0] or "")
                try:
                    limit = max(1, min(int(first("limit") or "20"), 1000))
                except ValueError:
                    limit = 20
                payload = provider(
                    search=first("search"),
                    state=first("state"),
                    agent=first("agent"),
                    provider=first("provider"),
                    limit=limit,
                )
                self._json(200, payload if isinstance(payload, dict) else {"tasks": payload})
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
            if not self._require_auth():
                return
            body = self._read_json()

            if path == "/voice/text":
                handler = self.voice_handler
                if handler is None:
                    self._json(503, {"error": "Browser voice handler unavailable."})
                    return
                result = handler(str(body.get("text", "")))
                self._json(200, result if isinstance(result, dict) else {"result": result})
                return

            if path == "/runtime/cancel":
                handler = self.cancel_active_task
                if handler is None:
                    self._json(503, {"error": "runtime cancellation unavailable"})
                    return
                reason = str(body.get("reason") or "cancelled from dashboard")
                result = handler(reason)
                self._json(200, result)
                return
            if path == "/settings":
                settings = UISettings(Path("data/ui_settings.json"))
                self._json(200, {"settings": settings.update(body)})
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
                self._json(
                    200,
                    {"result": invoke_realtime_tool(tool_name, args, self.tool_broker)},
                )
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
        runtime_status=None,
        cancel_active_task=None,
        runtime_tasks=None,
        auth_user: str | None = None,
        auth_password: str | None = None,
        tls_cert: str | None = None,
        tls_key: str | None = None,
    ) -> None:
        self.controller = controller
        self.host = host
        self.port = int(port)
        self.vrm_path = Path(vrm_path).expanduser().resolve() if vrm_path else None
        self.tool_broker = tool_broker
        self.voice_handler = voice_handler
        self.runtime_status = runtime_status
        self.cancel_active_task = cancel_active_task
        self.runtime_tasks = runtime_tasks
        self.auth_user = (auth_user if auth_user is not None else os.getenv("JENEFAR_AUTH_USER", "")).strip()
        self.auth_password = auth_password if auth_password is not None else os.getenv("JENEFAR_AUTH_PASSWORD", "")
        self.tls_cert = (tls_cert if tls_cert is not None else os.getenv("JENEFAR_TLS_CERT", "")).strip()
        self.tls_key = (tls_key if tls_key is not None else os.getenv("JENEFAR_TLS_KEY", "")).strip()
        self.allow_insecure_remote = os.getenv("JENEFAR_ALLOW_INSECURE_REMOTE", "").strip().lower() in {"1", "true", "yes"}
        loopback = self.host in {"127.0.0.1", "::1", "localhost"}
        if not loopback:
            if not self.auth_user or not self.auth_password:
                raise RuntimeError("Remote Jenefar requires JENEFAR_AUTH_USER and JENEFAR_AUTH_PASSWORD.")
            if not (self.tls_cert and self.tls_key) and not self.allow_insecure_remote:
                raise RuntimeError("Remote Jenefar requires JENEFAR_TLS_CERT and JENEFAR_TLS_KEY.")
        elif bool(self.tls_cert) != bool(self.tls_key):
            raise RuntimeError("JENEFAR_TLS_CERT and JENEFAR_TLS_KEY must be configured together.")
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._create_server()

    @property
    def url(self) -> str:
        scheme = "https" if self.tls_cert else "http"
        return f"{scheme}://{self.host}:{self.port}/"

    def _build_handler(self):
        controller = self.controller
        vrm_path = self.vrm_path
        tool_broker = self.tool_broker
        voice_handler = self.voice_handler
        runtime_status = self.runtime_status
        cancel_active_task = self.cancel_active_task
        runtime_tasks = self.runtime_tasks

        class Handler(_AvatarHandler):
            pass

        Handler.controller = controller
        Handler.vrm_path = vrm_path
        Handler.tool_broker = tool_broker
        # Functions stored on a handler class become bound methods. Keep the
        # injected browser voice callback as a static callable.
        Handler.voice_handler = staticmethod(voice_handler) if voice_handler is not None else None
        Handler.runtime_status = staticmethod(runtime_status) if runtime_status is not None else None
        Handler.cancel_active_task = staticmethod(cancel_active_task) if cancel_active_task is not None else None
        Handler.runtime_tasks = staticmethod(runtime_tasks) if runtime_tasks is not None else None
        Handler.auth_user = self.auth_user
        Handler.auth_password = self.auth_password
        return Handler

    def _create_server(self) -> None:
        if self._server is not None:
            return
        handler = self._build_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        if self.tls_cert and self.tls_key:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(self.tls_cert, self.tls_key)
            self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
        self.port = self._server.server_address[1]

    def start(self) -> None:
        if self._server is None:
            self._create_server()
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="jenefar-avatar-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        if server is None:
            return
        if self._thread is not None and self._thread.is_alive():
            server.shutdown()
        server.server_close()
        self._server = None
        self._thread = None
