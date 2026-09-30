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