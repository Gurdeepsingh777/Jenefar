from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from jenefar.rea.client import ReaMCPClient


def test_rea_bridge_defaults_to_enabled_with_official_server(monkeypatch):
    monkeypatch.setenv("JENEFAR_REA_ENABLED", "true")
    monkeypatch.delenv("JENEFAR_REA_COMMAND", raising=False)
    monkeypatch.delenv("JENEFAR_REA_ARGS", raising=False)
    client = ReaMCPClient()
    assert client.enabled is True
    assert client.command == "npx"
    assert client.args == ["-y", "rea-agents@6.5.0", "mcp"]
    client.close()


def test_rea_bridge_uses_documented_npx_arguments_from_existing_env(monkeypatch):
    monkeypatch.setenv("JENEFAR_REA_ENABLED", "true")
    monkeypatch.setenv("JENEFAR_REA_COMMAND", "npx")
    monkeypatch.setenv("JENEFAR_REA_ARGS", "-y,rea-agents@6.5.0,mcp")
    client = ReaMCPClient()
    assert client.args == ["-y", "rea-agents@6.5.0", "mcp"]
    client.close()


def test_rea_request_ends_with_real_newline_for_stdio_framing():
    import os
    from types import SimpleNamespace

    client = ReaMCPClient()
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    stdin = os.fdopen(input_write, "wb", buffering=0)
    stdout = os.fdopen(output_read, "rb", buffering=0)
    client._process = SimpleNamespace(
        stdin=stdin,
        stdout=stdout,
        poll=lambda: None,
    )
    try:
        os.write(
            output_write,
            b'{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{}}}\n',
        )
        result = client._request("initialize", {})
        written = os.read(input_read, 4096)
        assert result["serverInfo"] == {}
        assert written.endswith(b"\n")
        assert json.loads(written.decode("utf-8"))["method"] == "initialize"
    finally:
        client._process = None
        stdin.close()
        stdout.close()
        os.close(input_read)
        os.close(output_write)
        client.close()


def test_rea_bridge_can_be_disabled(monkeypatch):
    monkeypatch.setenv("JENEFAR_REA_ENABLED", "false")
    client = ReaMCPClient()
    status = client.status()
    assert status["enabled"] is False
    assert status["ready"] is False
    assert "disabled" in status["last_error"].lower()
    client.close()


def test_rea_schema_validator_rejects_missing_and_extra_arguments():
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}},
        "required": ["path"],
        "additionalProperties": False,
    }
    with pytest.raises(ValueError, match="Missing required"):
        ReaMCPClient._validate_arguments(schema, {})
    with pytest.raises(ValueError, match="Unexpected"):
        ReaMCPClient._validate_arguments(schema, {"path": "/tmp/x", "extra": True})
    with pytest.raises(ValueError, match="schema type"):
        ReaMCPClient._validate_arguments(schema, {"path": 123})
    with pytest.raises(ValueError, match="maximum"):
        ReaMCPClient._validate_arguments(schema, {"path": "/tmp/x", "limit": 11})


def test_rea_content_text_extracts_text_and_nontext_blocks():
    content = [
        {"type": "text", "text": "evidence"},
        {"type": "image", "data": "ignored"},
    ]
    result = ReaMCPClient._content_text(content)
    assert "evidence" in result
    assert "[REA returned image content]" in result


def test_rea_schema_call_requires_advertised_tool(monkeypatch):
    monkeypatch.setenv("JENEFAR_REA_ENABLED", "false")
    client = ReaMCPClient()
    with pytest.raises(RuntimeError, match="disabled"):
        client.call("unknown", {})
    client.close()


def test_rea_skill_is_available_in_jenefar_skill_manager(monkeypatch, tmp_path):
    from pathlib import Path
    from jenefar.skills.manager import SkillManager

    monkeypatch.setenv("JENEFAR_REA_SKILL_ENABLED", "true")
    manager = SkillManager(tmp_path / "state.json")
    registered = manager.get("rea_reverse_engineering")
    assert registered.connectors == ("rea",)
    assert Path(registered.source).name == "SKILL.md"
    assert "Call" in registered.system_prompt
    assert "rea_list_tools" in registered.system_prompt

def test_rea_client_preserves_multiple_jsonrpc_messages_from_one_read():
    import os
    import time
    from types import SimpleNamespace

    client = ReaMCPClient()
    read_fd, write_fd = os.pipe()
    stream = os.fdopen(read_fd, "rb", buffering=0)
    client._process = SimpleNamespace(stdout=stream, poll=lambda: None)
    try:
        os.write(
            write_fd,
            (
                '{"jsonrpc":"2.0","id":1,"result":{"first":true}}\n'
                '{"jsonrpc":"2.0","id":2,"result":{"second":true}}\n'
            ).encode("utf-8"),
        )
        first = client._read_message(time.monotonic() + 2)
        second = client._read_message(time.monotonic() + 2)
        assert first["id"] == 1
        assert first["result"]["first"] is True
        assert second["id"] == 2
        assert second["result"]["second"] is True
    finally:
        stream.close()
        os.close(write_fd)
        client._process = None
        client.close()
