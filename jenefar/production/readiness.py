from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from jenefar.core.config import ROOT
from jenefar.offline.local_llm import LocalLLMClient


def _online_providers() -> list[str]:
    return [
        name
        for name in (
            "OPENAI_API_KEY",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "OPENROUTER_API_KEY",
            "CEREBRAS_API_KEY",
        )
        if os.getenv(name, "").strip()
    ]


def check() -> dict:
    # Keep readiness consistent with the rest of the application: configuration
    # is rooted at the repository and .env is loaded before environment checks.
    load_dotenv(ROOT / ".env")

    warnings: list[str] = []
    failures: list[str] = []
    providers = _online_providers()

    explicit_local_url = os.getenv("JENEFAR_LOCAL_LLM_BASE_URL", "").strip()
    local_url = explicit_local_url or "http://127.0.0.1:11434/v1"
    parsed = urlparse(local_url)

    local_info = None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        failures.append("JENEFAR_LOCAL_LLM_BASE_URL is malformed")
    else:
        try:
            local_info = LocalLLMClient().detect()
        except Exception:
            local_info = None

    if local_info is not None:
        providers.append(f"local:{local_info.model}")
    elif not providers:
        if explicit_local_url:
            failures.append("configured local LLM provider is unreachable or has no model")
        else:
            failures.append("no online or local LLM provider configured")

    data_dir = Path(os.getenv("JENEFAR_DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir

    if not data_dir.exists():
        warnings.append("data directory missing; it will be created on first persistence")
    elif not data_dir.is_dir():
        failures.append("configured data directory is not a directory")

    if not os.getenv("JENEFAR_APPROVAL_SECRET"):
        warnings.append(
            "approval secret not explicitly configured; process-local secret will be generated"
        )

    if os.getenv("JENEFAR_TASK_HISTORY_PATH", "").startswith("/"):
        warnings.append("task history uses an absolute path; verify filesystem permissions")

    return {
        "ready": not failures,
        "providers": providers,
        "local_llm_configured": local_info is not None,
        "failures": failures,
        "warnings": warnings,
    }
