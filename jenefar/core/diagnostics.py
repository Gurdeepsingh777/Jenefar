"""Safe, read-only runtime diagnostics for the Jenefar local dashboard.

The report intentionally contains no API keys, environment values that can be
credentials, transcript text, or full task prompts. Probes are bounded and never
install packages, download models, or execute arbitrary shell commands.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _audio_status() -> dict[str, Any]:
    """Inspect PipeWire's visible sinks/sources without changing audio settings."""
    executable = shutil.which("wpctl")
    if not executable:
        return {
            "available": False,
            "output": {"status": "unknown", "default": None, "sinks": []},
            "input": {"status": "unknown", "default": None, "sources": []},
            "message": "wpctl is not installed; audio devices could not be inspected.",
        }
    try:
        result = subprocess.run(
            [executable, "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "output": {"status": "unknown", "default": None, "sinks": []},
            "input": {"status": "unknown", "default": None, "sources": []},
            "message": f"wpctl status failed: {type(exc).__name__}",
        }

    text = result.stdout or ""
    if result.returncode != 0 or not text.strip():
        return {
            "available": False,
            "output": {"status": "unknown", "default": None, "sinks": []},
            "input": {"status": "unknown", "default": None, "sources": []},
            "message": "PipeWire returned no usable device status.",
        }

    def section(title: str, following: str) -> list[dict[str, Any]]:
        start = text.find(title)
        if start < 0:
            return []
        start += len(title)
        end = text.find(following, start)
        body = text[start:] if end < 0 else text[start:end]
        items = []
        for line in body.splitlines():
            match = re.match(r"^\s*(\*)?\s*(\d+)\.\s+([^\[]+?)(?:\s+\[.*)?\s*$", line)
            if not match:
                continue
            name = match.group(3).strip()
            items.append({"id": int(match.group(2)), "name": name, "default": bool(match.group(1))})
        return items[:12]

    sinks = section("Sinks:", "Sources:")
    sources = section("Sources:", "Filters:")
    default_sink = next((item for item in sinks if item["default"]), None)
    default_source = next((item for item in sources if item["default"]), None)
    physical_sinks = [
        item for item in sinks
        if "dummy output" not in item["name"].casefold()
        and "monitor of" not in item["name"].casefold()
    ]
    if not sinks:
        output_state = "no_sink"
    elif default_sink and "dummy output" in default_sink["name"].casefold():
        output_state = "dummy_output_selected" if physical_sinks else "dummy_only"
    elif default_sink:
        output_state = "real_output_selected"
    elif physical_sinks:
        output_state = "physical_sink_not_default"
    else:
        output_state = "no_physical_sink"

    if not sources:
        input_state = "no_source"
    elif default_source and "monitor of" not in default_source["name"].casefold():
        input_state = "source_selected"
    else:
        input_state = "source_not_selected"

    return {
        "available": True,
        "output": {
            "status": output_state,
            "default": default_sink,
            "sinks": sinks,
        },
        "input": {
            "status": input_state,
            "default": default_source,
            "sources": sources,
        },
        "message": (
            "Audio status is observational only; a visible sink cannot prove the physical speaker is audible."
        ),
    }


def _ollama_status() -> dict[str, Any]:
    configured = os.getenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").strip()
    parsed = urlsplit(configured if "://" in configured else "http://" + configured)
    origin = urlunsplit((parsed.scheme or "http", parsed.netloc, "", "", ""))
    url = origin.rstrip("/") + "/api/tags"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=1.4) as response:
            import json
            payload = json.loads(response.read(1024 * 1024).decode("utf-8", errors="replace"))
        models = payload.get("models") if isinstance(payload, dict) else []
        names = [
            str(item.get("name") or item.get("model") or "").strip()
            for item in (models or [])
            if isinstance(item, dict)
        ]
        names = [name for name in names if name]
        configured_model = os.getenv("JENEFAR_LOCAL_LLM_FALLBACK_MODEL", "").strip()
        return {
            "available": True,
            "endpoint": origin,
            "model_count": len(names),
            "models": names[:12],
            "configured_fallback": configured_model or None,
            "fallback_installed": configured_model in names if configured_model else None,
            "message": "Ollama's model list is reachable; this does not guarantee a model will meet the task deadline.",
        }
    except Exception as exc:
        return {
            "available": False,
            "endpoint": origin,
            "model_count": 0,
            "models": [],
            "configured_fallback": os.getenv("JENEFAR_LOCAL_LLM_FALLBACK_MODEL", "").strip() or None,
            "fallback_installed": False,
            "message": f"Local Ollama model list is unavailable ({type(exc).__name__}).",
        }


def _whisper_status() -> dict[str, Any]:
    package_available = _module_available("faster_whisper")
    explicit_path = os.getenv("JENEFAR_LOCAL_STT_MODEL_PATH", "").strip()
    configured = os.getenv("JENEFAR_LOCAL_STT_MODEL", "base").strip() or "base"
    if explicit_path:
        model_path = Path(explicit_path).expanduser()
        cached = model_path.is_dir()
        cache_source = str(model_path) if cached else None
    else:
        candidates = list(dict.fromkeys([configured, "base", "tiny", "small"]))
        roots = []
        for env_name in ("HUGGINGFACE_HUB_CACHE", "HF_HUB_CACHE"):
            if os.getenv(env_name):
                roots.append(Path(os.environ[env_name]).expanduser())
        hf_home = os.getenv("HF_HOME", "").strip()
        if hf_home:
            roots.append(Path(hf_home).expanduser() / "hub")
        roots.append(Path.home() / ".cache" / "huggingface" / "hub")
        cache_source = None
        cached = False
        for root in roots:
            for model_name in candidates:
                repo_dir = root / f"models--Systran--faster-whisper-{model_name}"
                if repo_dir.is_dir():
                    cached = True
                    cache_source = model_name
                    break
            if cached:
                break
    ffmpeg = shutil.which("ffmpeg")
    if not package_available:
        status = "dependency_missing"
        message = "Run python run.py --setup-voice in the project's .venv."
    elif not cached:
        status = "model_cache_unverified"
        message = "Whisper is installed, but the configured model cache was not found by this quick check. Run python run.py --setup-voice once online."
    else:
        status = "ready"
        message = f"Local Whisper cache candidate is present ({cache_source})."
    return {
        "available": package_available and cached,
        "status": status,
        "package_installed": package_available,
        "configured_model": configured,
        "cache_verified": cached,
        "cache_model": cache_source,
        "ffmpeg_installed": bool(ffmpeg),
        "message": message if ffmpeg else message + " ffmpeg is also required for browser audio decoding; install it with sudo apt install ffmpeg.",
    }


def _timeout_settings() -> dict[str, int]:
    def read(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)).strip())
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    return {
        "task_seconds": read("JENEFAR_AGENT_TIMEOUT_SECONDS", 180, 10, 300),
        "online_window_seconds": read("JENEFAR_ONLINE_LLM_BUDGET_SECONDS", 20, 3, 120),
        "local_reserve_seconds": read("JENEFAR_LOCAL_FALLBACK_RESERVE_SECONDS", 45, 5, 120),
        "local_primary_seconds": read("JENEFAR_LOCAL_LLM_PRIMARY_TIMEOUT_SECONDS", 45, 5, 180),
        "local_retry_seconds": read("JENEFAR_LOCAL_LLM_RETRY_TIMEOUT_SECONDS", 120, 5, 300),
        "local_socket_ceiling_seconds": read("JENEFAR_LOCAL_LLM_TIMEOUT_SECONDS", 600, 5, 1800),
    }


def collect_runtime_diagnostics(
    orchestrator=None,
    *,
    browser_voice_enabled: bool = True,
) -> dict[str, Any]:
    """Return a credential-safe snapshot of voice, audio, models, desktop and budgets."""
    audio = _audio_status()
    whisper = _whisper_status()
    ollama = _ollama_status()

    desktop: dict[str, Any] = {"available": False, "message": "Desktop backend is not connected."}
    if orchestrator is not None:
        try:
            broker = getattr(orchestrator, "tool_broker", None)
            desktop_backend = getattr(broker, "desktop", None)
            if desktop_backend is not None and hasattr(desktop_backend, "backend_status"):
                raw = desktop_backend.backend_status()
                raw = raw if isinstance(raw, dict) else {"status": str(raw)}
                desktop = {
                    "available": str(raw.get("status", "")).casefold() in {"ready", "available", "ok"},
                    "status": str(raw.get("status") or "unknown"),
                    "session_type": raw.get("session_type"),
                    "input": raw.get("input"),
                    "capture": raw.get("capture"),
                    "screen": raw.get("screen"),
                    "message": str(raw.get("message") or raw.get("diagnosis") or "Desktop backend status collected."),
                }
        except Exception as exc:
            desktop = {"available": False, "message": f"Desktop status probe failed ({type(exc).__name__})."}

    active_task = None
    if orchestrator is not None:
        try:
            lifecycle = getattr(orchestrator, "task_lifecycle", None)
            active = lifecycle.active() if lifecycle is not None else None
            if active:
                active_task = {
                    "task_id": str(active.get("task_id") or ""),
                    "state": str(active.get("state") or ""),
                    "agent": str(active.get("agent") or ""),
                }
        except Exception:
            active_task = None

    checks = [
        {"id": "browser_voice", "status": "ready" if browser_voice_enabled else "disabled",
         "ok": bool(browser_voice_enabled), "message": "Browser voice bridge is enabled." if browser_voice_enabled else "Browser voice is disabled in configuration."},
        {"id": "whisper", "status": whisper["status"], "ok": whisper["available"], "message": whisper["message"]},
        {"id": "audio_output", "status": audio["output"]["status"],
         "ok": audio["output"]["status"] == "real_output_selected",
         "message": f"Default output: {((audio['output'].get('default') or {}).get('name') or 'none')}. {audio['message']}"},
        {"id": "audio_input", "status": audio["input"]["status"],
         "ok": audio["input"]["status"] == "source_selected",
         "message": f"Default input: {((audio['input'].get('default') or {}).get('name') or 'none')}."},
        {"id": "ollama", "status": "ready" if ollama["available"] else "unavailable",
         "ok": ollama["available"], "message": ollama["message"]},
        {"id": "desktop", "status": "ready" if desktop["available"] else "partial_or_unavailable",
         "ok": desktop["available"], "message": desktop.get("message", "")},
    ]
    issues = [item for item in checks if not item["ok"]]
    return {
        "status": "ready" if not issues else "needs_attention",
        "sampled_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "python": {
            "version": platform.python_version(),
            "venv_active": sys_prefix_is_venv(),
            "executable": os.path.basename(os.sys.executable),
        },
        "voice": {
            "browser_enabled": bool(browser_voice_enabled),
            "whisper": whisper,
            "tts": {
                "edge_tts_installed": _module_available("edge_tts"),
                "browser_speech_synthesis": "browser fallback (availability confirmed by client)",
            },
        },
        "audio": audio,
        "local_llm": ollama,
        "desktop": desktop,
        "timeouts": _timeout_settings(),
        "active_task": active_task,
        "checks": checks,
        "issues": [{"id": item["id"], "status": item["status"], "message": item["message"]} for item in issues],
    }


def sys_prefix_is_venv() -> bool:
    import sys
    return sys.prefix != sys.base_prefix


__all__ = ["collect_runtime_diagnostics"]
