from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlparse

def check() -> dict:
    warnings: list[str] = []
    failures: list[str] = []
    providers = [name for name in ("OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CEREBRAS_API_KEY") if os.getenv(name)]
    local_url = os.getenv("JENEFAR_LOCAL_LLM_BASE_URL", "").strip()

    # Jenefar's local Ollama runtime is the supported zero-key fallback.
    # If no explicit URL is configured, use the standard local Ollama endpoint
    # when it is reachable/configured by the local runtime.
    if not local_url:
        local_url = os.getenv("OLLAMA_HOST", "").strip()
        if not local_url:
            local_url = "http://127.0.0.1:11434"

    local_llm_configured = False
    if local_url:
        parsed = urlparse(local_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            failures.append("JENEFAR_LOCAL_LLM_BASE_URL is malformed")
        else:
            try:
                import urllib.request
                with urllib.request.urlopen(
                    local_url.rstrip("/") + "/api/tags",
                    timeout=2,
                ) as response:
                    local_llm_configured = 200 <= response.status < 300
            except Exception:
                local_llm_configured = False

    if not providers and not local_llm_configured:
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
        "local_llm_configured": local_llm_configured,
        "failures": failures,
        "warnings": warnings,
    }
