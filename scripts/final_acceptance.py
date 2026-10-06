#!/usr/bin/env python3
"""Final machine acceptance gate. Safe by default: no destructive actions."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
checks: dict[str, dict] = {}

def check(name, ok, detail):
    checks[name] = {"ok": bool(ok), "detail": detail}

def command(name, args, timeout=5):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        check(name, p.returncode == 0, (p.stdout or p.stderr).strip()[:500])
        return p
    except Exception as exc:
        check(name, False, f"{type(exc).__name__}: {exc}")
        return None

command("python", [sys.executable, "--version"])
command("compileall", [sys.executable, "-m", "compileall", "-q", "jenefar"])
command("doctor", [sys.executable, "run.py", "--doctor"], timeout=30)
command("production_readiness", [sys.executable, "run.py", "--production-readiness"], timeout=15)
command("integration_smoke", [sys.executable, "run.py", "--integration-smoke"], timeout=30)

if shutil.which("ollama"):
    p = command("ollama_version", ["ollama", "--version"])
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            payload = json.loads(response.read())
        models = [str(x.get("name") or x.get("model") or "") for x in payload.get("models", [])]
        vision = [m for m in models if any(x in m.lower() for x in ("qwen3-vl", "qwen2.5vl", "llava", "minicpm-v", "moondream"))]
        check("ollama_api", True, {"models": len(models), "vision_models": vision})
    except Exception as exc:
        check("ollama_api", False, f"{type(exc).__name__}: {exc}")
else:
    check("ollama", False, "ollama executable not found")

check("gpu_device", Path("/dev/dri/renderD128").exists(), "Intel/DRM render node")
if shutil.which("intel_gpu_top"):
    try:
        gpu_help = subprocess.run(
            ["intel_gpu_top", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        detail = (gpu_help.stdout or gpu_help.stderr).strip()[:1200]
        usable_help = (
            gpu_help.returncode == 0
            or "Usage: intel_gpu_top" in detail
            or "intel_gpu_top - Display a top-like summary" in detail
        )
        check("intel_gpu_top_help", usable_help, detail)
    except Exception as exc:
        check("intel_gpu_top_help", False, f"{type(exc).__name__}: {exc}")
else:
    check("intel_gpu_top_help", False, "install intel-gpu-tools for live Intel telemetry")

try:
    import psutil
    check("cpu_ram", psutil.cpu_count() > 0 and psutil.virtual_memory().total > 0,
          {"cpu_count": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 2)})
except Exception as exc:
    check("cpu_ram", False, f"{type(exc).__name__}: {exc}")

if os.getenv("JENEFAR_AVATAR_CHECK", "0").lower() in {"1", "true", "yes"}:
    host = os.getenv("JENEFAR_HOST", "127.0.0.1")
    port = os.getenv("JENEFAR_AVATAR_PORT", "8787")
    for name, path in {"health": "/health", "runtime": "/runtime/status", "readiness": "/production/readiness"}.items():
        try:
            with urlopen(f"http://{host}:{port}{path}", timeout=3) as response:
                check(f"avatar_{name}", response.status == 200, response.status)
        except Exception as exc:
            check(f"avatar_{name}", False, f"{type(exc).__name__}: {exc}")

failed = [name for name, item in checks.items() if not item["ok"]]
print(json.dumps({"ok": not failed, "failed": failed, "checks": checks}, indent=2, default=str))
raise SystemExit(1 if failed else 0)
