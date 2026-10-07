from __future__ import annotations

from pathlib import Path

from jenefar.production import readiness


def test_readiness_detects_local_ollama(monkeypatch):
    monkeypatch.setattr(readiness, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("JENEFAR_LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.setattr(
        readiness.LocalLLMClient,
        "detect",
        lambda self: readiness.LocalModelInfo(
            "http://127.0.0.1:11434/v1",
            "qwen3-vl:4b",
        ),
    )
    monkeypatch.setenv("JENEFAR_DATA_DIR", str(Path("data")))

    result = readiness.check()

    assert result["ready"] is True
    assert result["local_llm_configured"] is True
    assert result["providers"] == ["local:qwen3-vl:4b"]
    assert result["failures"] == []


def test_readiness_reports_explicit_local_provider_unreachable(monkeypatch):
    monkeypatch.setattr(readiness, "load_dotenv", lambda *args, **kwargs: None)
    for name in (
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "CEREBRAS_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv(
        "JENEFAR_LOCAL_LLM_BASE_URL",
        "http://127.0.0.1:9999/v1",
    )
    monkeypatch.setattr(readiness.LocalLLMClient, "detect", lambda self: None)

    result = readiness.check()

    assert result["ready"] is False
    assert result["local_llm_configured"] is False
    assert result["providers"] == []
    assert result["failures"] == [
        "configured local LLM provider is unreachable or has no model"
    ]


def test_readiness_uses_dotenv_and_root_relative_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(readiness, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.setenv("JENEFAR_LOCAL_LLM_BASE_URL", "not-a-url")
    monkeypatch.setenv("JENEFAR_DATA_DIR", str(tmp_path / "missing"))

    result = readiness.check()

    assert "JENEFAR_LOCAL_LLM_BASE_URL is malformed" in result["failures"]
    assert result["local_llm_configured"] is False
