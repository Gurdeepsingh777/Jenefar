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
            # wpctl prefixes tree drawing characters (│, ├─) before node IDs.
            match = re.match(
                r"^\s*[^0-9*]*?(\*)?\s*(\d+)\.\s+([^\[]+?)(?:\s+\[.*)?\s*$",
                line,
            )
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
    """Probe the configured local chat server without loading a model."""
    configured = os.getenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").strip()
    parsed = urlsplit(configured if "://" in configured else "http://" + configured)
    origin = urlunsplit((parsed.scheme or "http", parsed.netloc, "", "", ""))
    config_api = os.getenv("JENEFAR_LOCAL_LLM_API", "auto").strip().casefold()
    configured_path = parsed.path.rstrip("/")
    if configured_path.endswith("/v1"):
        openai_models_url = configured.rstrip("/") + "/models"
    else:
        openai_models_url = origin.rstrip("/") + "/v1/models"

    candidates: list[tuple[str, str]] = []
    if config_api not in {"openai", "openai-compatible", "openai_compatible"}:
        candidates.append((origin.rstrip("/") + "/api/tags", "ollama"))
    if config_api not in {"ollama"}:
        candidates.append((openai_models_url, "openai-compatible"))

    errors: list[str] = []
    for url, protocol in candidates:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=1.4) as response:
                import json
                payload = json.loads(response.read(1024 * 1024).decode("utf-8", errors="replace"))
            if protocol == "ollama":
                items = payload.get("models") if isinstance(payload, dict) else []
                names = [
                    str(item.get("name") or item.get("model") or "").strip()
                    for item in (items or [])
                    if isinstance(item, dict)
                ]
            else:
                items = payload.get("data") if isinstance(payload, dict) else []
                names = [
                    str(item.get("id") or "").strip()
                    for item in (items or [])
                    if isinstance(item, dict)
                ]
            names = [name for name in names if name]
            configured_model = (
                os.getenv("JENEFAR_LOCAL_LLM_MODEL_FAST", "").strip()
                or os.getenv("JENEFAR_LOCAL_LLM_MODEL", "").strip()
                or None
            )
            configured_fallback = os.getenv("JENEFAR_LOCAL_LLM_FALLBACK_MODEL", "").strip() or None
            return {
                "available": True,
                "protocol": protocol,
                "endpoint": origin,
                "model_count": len(names),
                "models": names[:12],
                "configured_model": configured_model,
                "configured_model_installed": configured_model in names if configured_model else None,
                "configured_fallback": configured_fallback,
                "fallback_installed": configured_fallback in names if configured_fallback else None,
                "message": (
                    f"Local {protocol} model list is reachable; this does not guarantee a model "
                    "will meet the task deadline."
                ),
            }
        except Exception as exc:
            errors.append(f"{protocol}: {type(exc).__name__}")

    detail = "; ".join(errors) if errors else "no compatible local API configured"
    return {
        "available": False,
        "protocol": None,
        "endpoint": origin,
        "model_count": 0,
        "models": [],
        "configured_model": (
            os.getenv("JENEFAR_LOCAL_LLM_MODEL_FAST", "").strip()
            or os.getenv("JENEFAR_LOCAL_LLM_MODEL", "").strip()
            or None
        ),
        "configured_model_installed": None,
        "configured_fallback": os.getenv("JENEFAR_LOCAL_LLM_FALLBACK_MODEL", "").strip() or None,
        "fallback_installed": False,
        "message": f"Local model list is unavailable ({detail}).",
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


def _online_provider_status(orchestrator=None) -> dict[str, Any]:
    """Report provider availability/cooldowns without exposing keys or endpoints."""
    try:
        from jenefar.core.provider_pool import ProviderPool
        base_pool = ProviderPool()
    except Exception as exc:
        return {
            "available": False,
            "order": [],
            "providers": [],
            "message": f"Provider routing status unavailable ({type(exc).__name__}).",
        }

    source_pools = []
    try:
        for agent in getattr(getattr(orchestrator, "router", None), "agents", []) or []:
            client = getattr(agent, "llm", None)
            source = getattr(client, "providers", None)
            if source is not None and source not in source_pools:
                source_pools.append(source)
    except Exception:
        source_pools = []
    if not source_pools:
        source_pools = [base_pool]

    import time
    now = time.monotonic()
    providers: list[dict[str, Any]] = []
    for name in base_pool.CONFIGS:
        try:
            configured = bool(base_pool.configured(name))
            cooldowns = [
                max(0.0, float(getattr(source, "cooldowns", {}).get(name, 0.0)) - now)
                for source in source_pools
            ]
            cooldown_seconds = max(cooldowns, default=0.0)
            samples: list[float] = []
            failures: list[int] = []
            for source in source_pools:
                samples.extend(
                    float(value)
                    for value in getattr(source, "latency_samples", {}).get(name, [])[-8:]
                )
                failures.append(int(getattr(source, "failure_samples", {}).get(name, 0)))
            samples = samples[-8:]
            model = base_pool.model(name, "fast")
            providers.append({
                "name": name,
                "configured": configured,
                "available": configured and cooldown_seconds <= 0.0,
                "cooldown_seconds": round(cooldown_seconds, 1),
                "model": model,
                "latency_samples": len(samples),
                "average_ms": round(sum(samples) / len(samples) * 1000, 1) if samples else None,
                "last_ms": round(samples[-1] * 1000, 1) if samples else None,
                "recent_failures": max(failures, default=0),
            })
        except Exception as exc:
            providers.append({
                "name": name,
                "configured": False,
                "available": False,
                "cooldown_seconds": 0.0,
                "model": None,
                "latency_samples": 0,
                "average_ms": None,
                "last_ms": None,
                "recent_failures": 0,
                "message": f"Provider status probe failed ({type(exc).__name__}).",
            })
    try:
        order = base_pool.order()
    except Exception:
        order = [item["name"] for item in providers]
    configured_count = sum(1 for item in providers if item["configured"])
    available_count = sum(1 for item in providers if item["available"])
    return {
        "available": bool(available_count),
        "order": order,
        "configured_count": configured_count,
        "available_count": available_count,
        "providers": providers,
        "message": (
            f"{available_count} configured cloud LLM provider(s) currently available; "
            f"{configured_count} configured in total. A provider may still reject a request due to remote quota/billing."
        ),
    }


def _voice_provider_status() -> dict[str, Any]:
    """Expose configured STT/TTS provider order, never credentials."""
    try:
        from jenefar.voice.provider import ProviderVoiceRuntime
        status = ProviderVoiceRuntime.audio_status()
    except Exception as exc:
        return {
            "stt": None,
            "tts": None,
            "message": f"Voice provider status unavailable ({type(exc).__name__}).",
        }
    return {
        "stt": status.get("stt"),
        "tts": status.get("tts"),
        "message": "Shows configured fallback order only; it cannot pre-verify provider quota or remote billing.",
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
    online_providers = _online_provider_status(orchestrator)
    voice_providers = _voice_provider_status()

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
        {"id": "cloud_llm", "status": "cloud_available" if online_providers["available"] else ("local_fallback" if ollama["available"] else "unavailable"),
         "ok": online_providers["available"] or ollama["available"],
         "message": online_providers["message"] + (" Local model list is reachable as a fallback." if not online_providers["available"] and ollama["available"] else "")},
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
            "stt": voice_providers.get("stt"),
            "tts": {
                **(voice_providers.get("tts") or {}),
                "edge_tts_installed": _module_available("edge_tts"),
                "browser_speech_synthesis": "browser fallback (actual capability is browser-reported)",
            },
            "provider_message": voice_providers.get("message"),
        },
        "audio": audio,
        "local_llm": ollama,
        "online_llm": online_providers,
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
