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

