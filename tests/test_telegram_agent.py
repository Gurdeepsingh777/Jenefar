from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from agent.core import AgentCore
from agent.llm import LLMError, LLMRateLimitError
from agent.tool_registry import ToolRegistry
from config import ConfigurationError, Settings, _parse_allowed_ids
from tools.github_tools import register_github_tools


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "telegram_bot_token": "test-telegram-token",
        "allowed_telegram_user_ids": frozenset({12345}),
        "llm_api_key": "test-llm-key",
        "llm_base_url": "https://api.example.test/v1",
        "llm_model_name": "test-model",
        "github_pat": "",
        "scratchpad_dir": tmp_path / "scratchpad",
        "skill_store_dir": tmp_path / "skills",
        "request_timeout_seconds": 3.0,
        "agent_timeout_seconds": 10.0,
        "max_tool_rounds": 4,
        "max_history_messages": 8,
        "max_input_chars": 1000,
        "max_tool_output_chars": 4000,
    }
    values.update(overrides)
    return Settings(**values)


def test_allowed_telegram_ids_are_validated_and_authorization_is_exact():
    assert _parse_allowed_ids("12345, 67890") == frozenset({12345, 67890})
    with pytest.raises(ConfigurationError):
        _parse_allowed_ids("")
    with pytest.raises(ConfigurationError):
        _parse_allowed_ids("12345,not-a-number")

    settings = Settings(
        telegram_bot_token="token",
        allowed_telegram_user_ids=frozenset({12345}),
        llm_api_key="key",
        llm_base_url="https://api.example.test/v1",
        llm_model_name="model",
    )
    assert settings.is_authorized(12345)
    assert not settings.is_authorized(67890)
    assert not settings.is_authorized(None)


def test_settings_reads_generic_api_environment_variables(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("ALLOWED_TELEGRAM_USER_IDS", "12345,67890")
    monkeypatch.setenv("LLM_API_KEY", "provider-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "free-model")
    monkeypatch.setenv("SCRATCHPAD_DIR", str(tmp_path / "notes"))
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    settings = Settings.from_env()
    assert settings.llm_api_key == "provider-key"
    assert settings.llm_base_url == "https://provider.example/v1"
    assert settings.llm_model_name == "free-model"
    assert settings.allowed_telegram_user_ids == frozenset({12345, 67890})


def test_registry_exports_openai_function_schema_and_handles_tool_errors():
    async def scenario():
        registry = ToolRegistry(max_output_chars=3000)

        @registry.tool(
            name="echo_value",
            description="Return the supplied test value.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        async def echo_value(arguments):
            return {"echo": arguments["value"]}

        @registry.tool(
            name="fail_for_test",
            description="Raise a test tool error.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        )
        async def fail_for_test(_arguments):
            raise RuntimeError("simulated tool failure")

        schema = registry.schemas()
        assert all(item["type"] == "function" for item in schema)
        assert {item["function"]["name"] for item in schema} == {"echo_value", "fail_for_test"}
        success = json.loads(await registry.execute("echo_value", {"value": "ok"}))
        assert success == {"ok": True, "result": {"echo": "ok"}}
        failure = json.loads(await registry.execute("fail_for_test", {}))
        assert failure["ok"] is False
        assert failure["error_type"] == "RuntimeError"

    asyncio.run(scenario())


def test_agent_react_loop_executes_tool_reads_observation_then_answers(tmp_path: Path):
    async def scenario():
        class FakeLLM:
            def __init__(self):
                self.calls = 0
                self.observations = []

            async def complete_chat(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    return {"choices": [{
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "echo_observation",
                                    "arguments": '{"value":"verified-result"}',
                                },
                            }],
                        },
                    }]}
                tool_messages = [item for item in messages if item.get("role") == "tool"]
                self.observations = tool_messages
                assert "verified-result" in tool_messages[-1]["content"]
                return {"choices": [{
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "I checked it and got verified-result."},
                }]}

        llm = FakeLLM()
        core = AgentCore(make_settings(tmp_path), llm=llm)

        @core.tools.tool(
            name="echo_observation",
            description="Return an observable test result.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        async def echo_observation(arguments):
            return {"observed": arguments["value"]}

        answer = await core.respond(12345, "Check the result and tell me what was observed.")
        assert answer == "I checked it and got verified-result."
        assert llm.calls == 2
        assert llm.observations[-1]["tool_call_id"] == "call-1"
        assert core.status(12345)["remembered_messages"] == 2
        await core.aclose()

    asyncio.run(scenario())


def test_agent_clear_resets_only_the_requested_user_memory(tmp_path: Path):
    async def scenario():
        class FakeLLM:
            async def complete_chat(self, messages, tools=None):
                return {"choices": [{"message": {"role": "assistant", "content": "Done."}}]}

        core = AgentCore(make_settings(tmp_path), llm=FakeLLM())
        await core.respond(12345, "Remember the current topic for this conversation.")
        await core.respond(77777, "A separate user's context.")
        assert core.status(12345)["remembered_messages"] == 2
        assert core.clear_memory(12345) is True
        assert core.status(12345)["remembered_messages"] == 0
        assert core.status(77777)["remembered_messages"] == 2
        await core.aclose()

    asyncio.run(scenario())


def test_scratchpad_persists_notes_and_rejects_path_traversal(tmp_path: Path):
    async def scenario():
        core = AgentCore(make_settings(tmp_path), llm=object())
        write = json.loads(await core.tools.execute(
            "scratchpad_write",
            {"path": "notes/task.md", "content": "remember this workflow"},
        ))
        assert write["ok"] is True

        read = json.loads(await core.tools.execute("scratchpad_read", {"path": "notes/task.md"}))
        assert read["ok"] is True
        assert read["result"]["content"] == "remember this workflow"

        traversal = json.loads(await core.tools.execute(
            "scratchpad_write",
            {"path": "../escape.txt", "content": "no"},
        ))
        assert traversal["ok"] is False
        await core.aclose()

    asyncio.run(scenario())


def test_fetch_url_rejects_loopback_before_network_access(tmp_path: Path):
    async def scenario():
        core = AgentCore(make_settings(tmp_path), llm=object())
        result = json.loads(await core.tools.execute("fetch_url", {"url": "http://127.0.0.1:8080/private"}))
        assert result["ok"] is False
        assert "blocked" in result["error"].lower()
        await core.aclose()

    asyncio.run(scenario())


def test_github_toolset_is_registered_and_gracefully_reports_missing_pat(tmp_path: Path):
    async def scenario():
        settings = make_settings(tmp_path, github_pat="")
        registry = ToolRegistry()
        register_github_tools(registry, settings)
        assert {"list_repos", "read_file", "create_or_update_file", "create_repo", "manage_issues"} <= set(registry.names())
        result = json.loads(await registry.execute("list_repos", {}))
        assert result["ok"] is False
        assert "GITHUB_PAT" in result["error"]

    asyncio.run(scenario())


def test_llm_rate_limit_error_is_a_distinct_actionable_exception():
    assert issubclass(LLMRateLimitError, LLMError)
    assert "rate limit" in str(LLMRateLimitError("rate limit reached"))


def test_file_write_tool_schema_requires_explicit_path_content_and_commit_message(tmp_path: Path):
    registry = ToolRegistry()
    register_github_tools(registry, make_settings(tmp_path, github_pat="token"))
    schema = next(item["function"] for item in registry.schemas() if item["function"]["name"] == "create_or_update_file")
    assert set(schema["parameters"]["required"]) == {"path", "content", "message"}
    assert schema["parameters"]["additionalProperties"] is False



def test_persistent_skill_survives_store_restart_and_matches_keywords(tmp_path: Path):
    from agent.skills import SkillStore

    first = SkillStore(tmp_path / "permanent-skills")
    saved = first.save(
        name="Python Test Workflow",
        description="Run and verify Python unit tests.",
        keywords=["python", "pytest", "unit tests"],
        instructions="Inspect the current project, run the registered test tools, and verify their output.",
    )
    assert saved["saved"] is True
    assert saved["executable_code_installed"] is False

    second = SkillStore(tmp_path / "permanent-skills")
    matched = second.matching("Please use pytest to validate this Python project.")
    assert any(item["name"] == "python_test_workflow" for item in matched)
    assert "verify their output" in matched[0]["instructions"]


def test_successful_multi_tool_task_is_auto_learned_and_reused(tmp_path: Path):
    async def scenario():
        class FakeLLM:
            def __init__(self):
                self.calls = 0
                self.system_message = ""

            async def complete_chat(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    self.system_message = messages[0]["content"]
                    return {"choices": [{
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-read-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_python_versions",
                                        "arguments": "{}",
                                    },
                                },
                                {
                                    "id": "call-read-2",
                                    "type": "function",
                                    "function": {
                                        "name": "read_dependency_manifest",
                                        "arguments": "{}",
                                    },
                                },
                            ],
                        },
                    }]}
                return {"choices": [{
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "I checked the Python dependency details and summarized the results.",
                    },
                }]}

        llm = FakeLLM()
        core = AgentCore(make_settings(tmp_path), llm=llm)

        @core.tools.tool(
            name="read_python_versions",
            description="Read Python version information.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        )
        async def read_python_versions(_args):
            return {"python": "3.x"}

        @core.tools.tool(
            name="read_dependency_manifest",
            description="Read dependency metadata.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        )
        async def read_dependency_manifest(_args):
            return {"dependencies": ["pytest", "httpx"]}

        answer = await core.respond(
            12345,
            "Check Python package dependencies and summarize version details.",
        )
        assert "summarized the results" in answer
        learned = core.skills.list()
        assert any(item["source"] == "auto_verified_workflow" for item in learned)
        matched = core.skills.matching("Python dependency version details")
        assert matched
        assert "Relevant persistent SKILL.md guidance" in core._system_message("Python dependency version details")
        await core.aclose()

    asyncio.run(scenario())


def test_skill_store_refuses_credential_assignments_and_raw_targets(tmp_path: Path):
    from agent.skills import SkillStore

    store = SkillStore(tmp_path / "skills")
    with pytest.raises(ValueError):
        store.save(
            name="unsafe-token-skill",
            description="Example only",
            keywords=["example"],
            instructions="api_key = sk-test-do-not-save",
        )
    with pytest.raises(ValueError):
        store.save(
            name="target-specific-skill",
            description="Example only",
            keywords=["network"],
            instructions="Scan https://example.com and reuse that target.",
        )
