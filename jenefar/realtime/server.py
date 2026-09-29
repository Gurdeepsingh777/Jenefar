from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

from jenefar.tools.broker import ToolBroker


class RealtimeSessionError(RuntimeError):
    pass


def create_ephemeral_session(tool_broker: ToolBroker | None = None) -> dict[str, object]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RealtimeSessionError("OPENAI_API_KEY is not configured.")

    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1")
    voice = os.getenv("OPENAI_REALTIME_VOICE", os.getenv("OPENAI_TTS_VOICE", "alloy"))
    instructions = os.getenv(
        "OPENAI_REALTIME_INSTRUCTIONS",
        "You are Jenefar, a precise voice-first multi-agent assistant.",
    )
    broker = tool_broker or ToolBroker()
    tools = broker.schemas(
        allow_action_tools=True,
        include_confirmation_tools=True,
    )
    payload = {
        "session": {
            "type": "realtime",
            "model": model,
            "instructions": instructions,
            "audio": {"output": {"voice": voice}},
            "tools": tools,
        }
    }
    req = request.Request(
        "https://api.openai.com/v1/realtime/client_secrets",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RealtimeSessionError(
            f"Realtime session creation failed: {type(exc).__name__}: {exc}"
        ) from exc

    value = result.get("value")
    if not value:
        raise RealtimeSessionError(
            "Realtime session response did not contain an ephemeral client secret."
        )
    return {"value": value, "model": model}


def invoke_realtime_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute only read-only tools exposed to browser Realtime sessions."""
    broker = ToolBroker()
    allowed = {item["name"] for item in broker.schemas(
        allow_action_tools=False,
        include_confirmation_tools=False,
    )}
    if name not in allowed:
        raise RealtimeSessionError(f"Realtime tool '{name}' is not exposed by policy.")
    return broker.invoke(name, arguments)
