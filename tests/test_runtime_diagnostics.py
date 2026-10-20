from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from jenefar.core import diagnostics


def test_audio_diagnostics_detect_dummy_output_and_physical_speaker(monkeypatch):
    output = """PipeWire 'pipewire-0'
Audio
 ├─ Sinks:
 │  *   35. Dummy Output [vol: 0.80]
 │      57. Speaker – 500 Series Chipset Family [vol: 0.80]
 ├─ Sources:
 │  *   54. Digital Microphone [vol: 0.77]
 ├─ Filters:
"""
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/bin/wpctl" if name == "wpctl" else None)
    monkeypatch.setattr(
        diagnostics.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, output, ""),
    )

    result = diagnostics._audio_status()
    assert result["output"]["status"] == "dummy_output_selected"
    assert result["output"]["default"]["name"] == "Dummy Output"
    assert result["input"]["status"] == "source_selected"
    assert any("Speaker" in item["name"] for item in result["output"]["sinks"])


def test_audio_diagnostics_recognizes_real_default_output(monkeypatch):
    output = """Audio
 ├─ Sinks:
 │      35. Dummy Output [vol: 0.80]
 │  *   57. Speaker – 500 Series Chipset Family [vol: 0.80]
 ├─ Sources:
 │  *   54. Digital Microphone [vol: 0.77]
 ├─ Filters:
"""
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/bin/wpctl" if name == "wpctl" else None)
    monkeypatch.setattr(
        diagnostics.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, output, ""),
    )
    result = diagnostics._audio_status()
    assert result["output"]["status"] == "real_output_selected"
    assert result["output"]["default"]["id"] == 57


def test_runtime_diagnostics_are_structured_and_do_not_expose_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-value")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-gemini-value")
    monkeypatch.setattr(diagnostics, "_audio_status", lambda: {
        "available": True,
        "output": {"status": "real_output_selected", "default": {"name": "Speaker"}, "sinks": []},
        "input": {"status": "source_selected", "default": {"name": "Microphone"}, "sources": []},
        "message": "Audio inspection complete.",
    })
    monkeypatch.setattr(diagnostics, "_whisper_status", lambda: {
        "available": True, "status": "ready", "package_installed": True,
        "configured_model": "base", "cache_verified": True, "cache_model": "base",
        "ffmpeg_installed": True, "message": "Whisper ready.",
    })
    monkeypatch.setattr(diagnostics, "_ollama_status", lambda: {
        "available": True, "endpoint": "http://127.0.0.1:11434",
        "model_count": 1, "models": ["qwen3:4b"], "configured_fallback": "qwen3:4b",
        "fallback_installed": True, "message": "Ollama is available.",
    })
    monkeypatch.setattr(diagnostics, "_module_available", lambda _name: True)

    orchestrator = SimpleNamespace(
        tool_broker=SimpleNamespace(
            desktop=SimpleNamespace(backend_status=lambda: {
                "status": "ready", "input": "ready", "capture": "ready",
                "message": "Desktop backend ready.",
            })
        ),
        task_lifecycle=SimpleNamespace(active=lambda: None),
    )
    report = diagnostics.collect_runtime_diagnostics(
        orchestrator,
        browser_voice_enabled=True,
    )
    serialized = json.dumps(report)

    assert report["status"] == "ready"
    assert report["local_llm"]["models"] == ["qwen3:4b"]
    assert report["timeouts"]["task_seconds"] >= 10
    assert report["checks"]
    assert "secret-openai-value" not in serialized
    assert "secret-gemini-value" not in serialized


def test_runtime_diagnostics_handles_missing_audio_tools(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)
    result = diagnostics._audio_status()
    assert result["available"] is False
    assert result["output"]["status"] == "unknown"
    assert "wpctl" in result["message"]
