from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlparse

def check() -> dict:
    warnings: list[str] = []
    failures: list[str] = []
    providers = [name for name in ("OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CEREBRAS_API_KEY") if os.getenv(name)]
    local_url = os.getenv("JENEFAR_LOCAL_LLM_BASE_URL", "")
    if not providers and not local_url:
        failures.append("no online or local LLM provider configured")
    if local_url:
        parsed = urlparse(local_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            failures.append("JENEFAR_LOCAL_LLM_BASE_URL is malformed")
    data_dir = Path(os.getenv("JENEFAR_DATA_DIR", "data"))
    if not data_dir.exists():
        warnings.append("data directory missing; it will be created on first persistence")
    elif not data_dir.is_dir():
        failures.append("configured data directory is not a directory")
    if not os.getenv("JENEFAR_APPROVAL_SECRET"):
        warnings.append("approval secret not explicitly configured; process-local secret will be generated")
    if os.getenv("JENEFAR_TASK_HISTORY_PATH", "").startswith("/"):
        warnings.append("task history uses an absolute path; verify filesystem permissions")
    return {
        "ready": not failures,
        "providers": providers,
        "local_llm_configured": bool(local_url),
        "failures": failures,
        "warnings": warnings,
    }
