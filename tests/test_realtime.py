import json

from jenefar.realtime.server import (
    RealtimeSessionError,
    create_ephemeral_session,
    invoke_realtime_tool,
)
from jenefar.tools.broker import ToolBroker
from jenefar.tools.registry import ToolSpec


def test_realtime_tool_approval_uses_persistent_broker():
    broker = ToolBroker(require_confirmation=True)
    broker.registry.register(ToolSpec(
        name="test_realtime_action",
        description="test",
        handler=lambda _args: "done",
        requires_confirmation=True,
        action=True,
    ))

    response = json.loads(
        invoke_realtime_tool("test_realtime_action", {}, broker)
    )
    assert response["status"] == "approval_required"
    pending_id = response["pending_id"]
    assert pending_id in broker.pending

    approved = json.loads(broker.approve(pending_id))
    assert approved == {"status": "ok", "result": "done"}


def test_realtime_read_only_direct_call_is_supported():
    response = json.loads(invoke_realtime_tool("local_time", {}, ToolBroker()))
    assert response["status"] == "ok"
    assert "timezone" in response["result"]


def test_realtime_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        create_ephemeral_session()
    except RealtimeSessionError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing API key error")
