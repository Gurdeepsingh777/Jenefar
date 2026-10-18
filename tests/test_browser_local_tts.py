from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from jenefar.voice.browser import BrowserVoiceBridge


def test_local_piper_tts_writes_browser_playable_wav_without_network(monkeypatch, tmp_path):
    model = tmp_path / "licensed-voice.onnx"
    model.write_bytes(b"model-placeholder")
    monkeypatch.setenv("JENEFAR_LOCAL_TTS_MODEL", str(model))
    monkeypatch.setenv("JENEFAR_LOCAL_TTS_TIMEOUT_SECONDS", "15")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/piper" if name == "piper" else None)

    captured = {}

    def fake_run(args, *, input, stdout, stderr, timeout, check):
        captured["args"] = args
        captured["input"] = input
        captured["timeout"] = timeout
        output_path = args[args.index("--output_file") + 1]
        Path(output_path).write_bytes(b"RIFF" + b"fake-wav-data")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    bridge = object.__new__(BrowserVoiceBridge)
    bridge._piper_tts_disabled = False

    encoded, mime = bridge._synthesize_local_piper_audio("Hello Jenefar")

    assert mime == "audio/wav"
    assert base64.b64decode(encoded).startswith(b"RIFF")
    assert captured["args"][:3] == ["/usr/bin/piper", "--model", str(model)]
    assert captured["input"] == b"Hello Jenefar"
    assert captured["timeout"] == 15
    assert not Path(captured["args"][captured["args"].index("--output_file") + 1]).exists()


def test_browser_voice_tries_configured_local_piper_before_edge(monkeypatch):
    for name in (
        "OPENAI_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY", "API_KEY",
        "LLM_BASE_URL", "BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    bridge = object.__new__(BrowserVoiceBridge)
    bridge._openai_tts_disabled = False
    bridge._gemini_tts_disabled = False
    bridge._piper_tts_disabled = False
    monkeypatch.setattr(bridge, "_synthesize_gemini_audio", lambda _text: ("", ""))
    monkeypatch.setattr(
        bridge, "_synthesize_local_piper_audio",
        lambda _text: (base64.b64encode(b"local-wav").decode("ascii"), "audio/wav"),
    )
    monkeypatch.setattr(
        bridge, "_synthesize_edge_audio",
        lambda _text: (_ for _ in ()).throw(AssertionError("Edge TTS should not be needed")),
    )

    encoded, mime = bridge._synthesize_browser_audio("Offline response")

    assert base64.b64decode(encoded) == b"local-wav"
    assert mime == "audio/wav"


def test_missing_configured_piper_model_is_cached_as_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("JENEFAR_LOCAL_TTS_MODEL", str(tmp_path / "missing.onnx"))
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/piper" if name == "piper" else None)
    bridge = object.__new__(BrowserVoiceBridge)
    bridge._piper_tts_disabled = False

    assert bridge._synthesize_local_piper_audio("Hello") == ("", "")
    assert bridge._piper_tts_disabled is True
