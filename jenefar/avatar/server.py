from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jenefar.avatar.controller import AvatarController
from jenefar.avatar.settings import UISettings
from jenefar.avatar.system_metrics import read_system_metrics
from jenefar.core.model_router import ModelRouter
from jenefar.core.model_catalog import list_provider_models
from jenefar.core.model_ids import normalize_model_id
from jenefar.core.provider_pool import ProviderPool
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
    voice_audio_handler = None
    approval_handler = None
    rejection_handler = None

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Browser tabs can close or cancel an in-flight fetch. The client
            # is already gone, so attempting to send a second error response
            # only creates another BrokenPipeError and noisy server traceback.
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
        parsed_url = urlparse(self.path)
        path = parsed_url.path or "/"
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
            if path == "/system/metrics":
                self._json(200, read_system_metrics())
                return
            if path == "/model/status":
                pool = ProviderPool()
                states = pool.status("fast")
                providers = []
                for name, state in states.items():
                    if not state["configured"]:
                        continue
                    catalog = list_provider_models(name, pool)
                    providers.append({
                        "id": name,
                        "label": name.replace("_", " ").title(),
                        "model": state["model"],
                        "available": state["available"],
                        "models": catalog.get("models", []),
                        "catalog_source": catalog.get("source", "unknown"),
                        "catalog_diagnostic": catalog.get("diagnostic"),
                    })
                override = ModelRouter.runtime_override()
                selected = ModelRouter().resolve("fast")
                active_provider = (override or {}).get("provider", "") or selected.provider or ""
                if active_provider not in pool.CONFIGS:
                    active_provider = next(
                        (
                            name for name in pool.order()
                            if pool.configured(name)
                            and normalize_model_id(pool.model(name, "fast"), name) == selected.model
                        ),
                        "",
                    )
                if not active_provider:
                    active_provider = next(
                        (name for name in pool.order() if pool.configured(name)), ""
                    )
                self._json(
                    200,
                    {
                        "active": {
                            "provider": active_provider,
                            "model": selected.model,
                            "source": selected.source,
                        },
                        "providers": providers,
                        "runtime_override": bool(override),
                    },
                )
                return
            if path == "/security/scope":
                broker = self.tool_broker
                scope = getattr(broker, "scope", None) if broker is not None else None
                if scope is None:
                    self._json(503, {
                        "configured": False,
                        "authorized_targets": [],
                        "last_error": "Security scope is not wired into this runtime.",
                    })
                    return
                targets = list(getattr(scope, "allowed_targets", []) or [])
                payload = {
                    "configured": bool(targets),
                    "target_count": len(targets),
                    "authorized_targets": targets,
                    "deny_by_default": not bool(targets),
                }
                query_targets = parse_qs(parsed_url.query).get("target", [])
                if query_targets:
                    target = query_targets[0]
                    payload["check"] = {
                        "target": target,
                        "allowed": bool(scope.allows(target)),
                        "message": scope.explain(target),
                    }
                self._json(200, payload)
                return
            if path == "/rea/status":
                broker = self.tool_broker
                if broker is None or not hasattr(broker, "rea_connector"):
                    self._json(503, {"enabled": False, "ready": False, "connected": False,
                                     "last_error": "REA connector is not wired into this runtime."})
                    return
                status = broker.rea_connector.status()
                try:
                    status["skill_registered"] = True
                    status["skill_enabled"] = broker.skills.is_enabled("rea_reverse_engineering")
                except Exception:
                    status["skill_registered"] = False
                    status["skill_enabled"] = False
                self._json(200, status)
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
            if path == "/voice/audio":
                handler = self.voice_audio_handler
                if handler is None:
                    self._json(503, {"error": "Browser microphone audio transcription is unavailable."})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                except ValueError:
                    self._json(400, {"error": "Invalid Content-Length."})
                    return
                if length <= 0:
                    self._json(400, {"error": "No audio payload was received."})
                    return
                if length > 12 * 1024 * 1024:
                    self._json(413, {"error": "Audio recording is too large (limit: 12 MiB)."})
                    return
                audio = self.rfile.read(length)
                if len(audio) != length:
                    self._json(400, {"error": "The microphone audio upload was incomplete."})
                    return
                result = handler(audio, self.headers.get("Content-Type", "audio/webm"))
                payload = result if isinstance(result, dict) else {"result": result}
                self._json(200 if not payload.get("error") else 422, payload)
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

            if path == "/model/select":
                provider = str(body.get("provider", "")).strip().lower()
                model = str(body.get("model", "")).strip()
                pool = ProviderPool()
                if provider not in pool.CONFIGS:
                    self._json(400, {"error": "Choose a supported provider."})
                    return
                if not pool.configured(provider):
                    self._json(
                        400,
                        {"error": f"{provider} is not configured. Add its API key to .env first."},
                    )
                    return
                model = normalize_model_id(model, provider)
                if not model or len(model) > 160 or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}", model
                ):
                    self._json(
                        400,
                        {"error": "Enter a valid model ID (letters, numbers, . _ : / + -)."},
                    )
                    return
                catalog = list_provider_models(provider, pool)
                if catalog.get("source") == "provider-api" and model not in catalog.get("models", []):
                    suggestions = ", ".join(catalog.get("models", [])[:5])
                    detail = f" Use an available model: {suggestions}." if suggestions else ""
                    self._json(
                        400,
                        {"error": f"Model '{model}' was not returned by the {provider} API for this key.{detail}"},
                    )
                    return
                ModelRouter.set_runtime_override(model, provider)
                self._json(
                    200,
                    {
                        "status": "ok",
                        "active": {"provider": provider, "model": model, "source": "browser-runtime"},
                    },
                )
                return

            if path == "/rea/connect":
                broker = self.tool_broker
                if broker is None or not hasattr(broker, "rea_connector"):
                    self._json(503, {"status": "error", "error": "REA connector is not wired into this runtime."})
                    return
                try:
                    result = broker.rea_connector.list_tools()
                    self._json(200, {
                        "status": "connected",
                        "connected": True,
                        "ready": True,
                        "skill_registered": True,
                        "skill_enabled": broker.skills.is_enabled("rea_reverse_engineering"),
                        "server": result.get("server", "rea"),
                        "tool_count": result.get("count", len(result.get("tools", []))),
                        "tool_examples": [item.get("name") for item in result.get("tools", [])[:8]],
                    })
                except Exception as exc:
                    self._json(502, {
                        "status": "error",
                        "connected": False,
                        "ready": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
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
                handler = getattr(self, "rejection_handler", None)
                result = handler(pending_id) if handler is not None else self.tool_broker.reject(pending_id)
                self._json(200, {"result": result})
                return

            if path == "/realtime/session":
                self._json(200, create_ephemeral_session(self.tool_broker))
                return

            if path == "/realtime/tool":
                pending_id = str(body.get("approve_id", "")).strip()
                if pending_id and self.tool_broker:
                    handler = getattr(self, "approval_handler", None)
                    owner = getattr(handler, "__self__", None) if handler is not None else None
                    # The browser voice handler wraps the orchestrator; resolve both
                    # shapes and clear stale scan state before this specific approval.
                    scan_owner = getattr(owner, "orchestrator", owner)
                    if owner is scan_owner and scan_owner is not None and hasattr(scan_owner, "_latest_scan_result"):
                        scan_owner._latest_scan_result = None
                    result = handler(pending_id) if handler is not None else self.tool_broker.approve(pending_id)
                    payload = {"result": result}
                    # Direct host discovery/port-scan approvals return the structured
                    # scan as a response fallback as well as through the live SSE path.
                    scan_data = getattr(scan_owner, "_latest_scan_result", None)
                    if isinstance(scan_data, dict) and scan_data.get("kind") in {"host_discovery", "port_scan"}:
                        if not isinstance(result, dict) or result.get("structured_scan"):
                            payload["structured_scan"] = scan_data
                        elif isinstance(result, str):
                            payload["structured_scan"] = scan_data
                    self._json(200, payload)
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
        voice_audio_handler=None,
        approval_handler=None,
        rejection_handler=None,
    ) -> None:
        self.controller = controller
        self.host = host
        self.port = int(port)
        self.vrm_path = Path(vrm_path).expanduser().resolve() if vrm_path else None
        self.tool_broker = tool_broker
        self.voice_handler = voice_handler
        self.voice_audio_handler = voice_audio_handler
        self.approval_handler = approval_handler
        self.rejection_handler = rejection_handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._create_server()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def _build_handler(self):
        controller = self.controller
        vrm_path = self.vrm_path
        tool_broker = self.tool_broker
        voice_handler = self.voice_handler
        voice_audio_handler = self.voice_audio_handler
        approval_handler = self.approval_handler
        rejection_handler = self.rejection_handler

        class Handler(_AvatarHandler):
            pass

        Handler.controller = controller
        Handler.vrm_path = vrm_path
        Handler.tool_broker = tool_broker
        # Functions stored on a handler class become bound methods. Keep the
        # injected browser voice callback as a static callable.
        Handler.voice_handler = staticmethod(voice_handler) if voice_handler is not None else None
        Handler.voice_audio_handler = staticmethod(voice_audio_handler) if voice_audio_handler is not None else None
        Handler.approval_handler = staticmethod(approval_handler) if approval_handler is not None else None
        Handler.rejection_handler = staticmethod(rejection_handler) if rejection_handler is not None else None
        return Handler

    def _create_server(self) -> None:
        if self._server is not None:
            return
        handler = self._build_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
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
