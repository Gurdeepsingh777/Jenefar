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
    voice = os.getenv("OPENAI_REALTIME_VOICE", os.getenv("OPENAI_TTS_VOICE", "coral"))
    instructions = os.getenv(
        "OPENAI_REALTIME_INSTRUCTIONS",
        (
            "You are Jenefar, a warm, natural, proactive voice-first female assistant. "
            "Speak in everyday Roman Hinglish as if talking naturally with one person. "
            "Prefer conversational Indian phrasing, gentle pauses, empathy, and practical solutions. "
            "When a safe available tool can answer or perform the task, use it instead of telling the user "
            "to do the work manually. If one supported method fails, try another supported method. "
            "Keep code, commands, filenames, APIs, and technical terminology unchanged. "
            "Never output Devanagari."
        ),
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


def invoke_realtime_tool(
    name: str,
    arguments: dict[str, Any],
    tool_broker: ToolBroker | None = None,
) -> str:
    """Invoke a Realtime tool through the session's persistent broker.

    A persistent broker is required for action/approval tools because pending
    approval IDs are stored on the broker instance. Direct callers without a
    broker are limited to read-only, non-confirmation tools.
    """
    broker = tool_broker or ToolBroker()
    spec = broker.registry.get(name)

    if tool_broker is None and (spec.action or spec.requires_confirmation):
        raise RealtimeSessionError(
            f"Realtime tool '{name}' requires the active avatar session broker."
        )

    return broker.invoke(name, arguments)
