from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


def _config() -> dict[str, str]:
    """Resolve process env first, then the project .env as a deployment fallback."""
    values: dict[str, str] = {}
    env_path = Path(os.getenv("JENEFAR_ENV_FILE", ".env")).expanduser()
    if env_path.is_file():
        values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    values.update({k: v for k, v in os.environ.items() if k.startswith(("JENEFAR_", "OLLAMA_", "OPENAI_", "GROQ_", "GEMINI_", "OPENROUTER_", "CEREBRAS_"))})
    return values


def check() -> dict:
    cfg = _config()
    warnings: list[str] = []
    failures: list[str] = []
    providers = [name for name in ("OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CEREBRAS_API_KEY") if cfg.get(name)]
    local_url = cfg.get("JENEFAR_LOCAL_LLM_BASE_URL", "").strip()
    if not local_url:
        local_url = cfg.get("OLLAMA_HOST", "").strip()
        if not local_url:
            local_url = "http://127.0.0.1:11434"

    local_llm_configured = False
    parsed = urlparse(local_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        failures.append("JENEFAR_LOCAL_LLM_BASE_URL is malformed")
    else:
        try:
            import urllib.request
            health_base = local_url.rstrip("/")
            if health_base.endswith("/v1"):
                health_base = health_base[:-3].rstrip("/")
            with urllib.request.urlopen(health_base + "/api/tags", timeout=2) as response:
                local_llm_configured = 200 <= response.status < 300
        except Exception:
            local_llm_configured = False

    if not providers and not local_llm_configured:
        failures.append("no online or local LLM provider configured")
    data_dir = Path(cfg.get("JENEFAR_DATA_DIR", "data"))
    if not data_dir.exists():
        warnings.append("data directory missing; it will be created on first persistence")
    elif not data_dir.is_dir():
        failures.append("configured data directory is not a directory")

    approval_secret = cfg.get("JENEFAR_APPROVAL_SECRET", "").strip()
    if not approval_secret:
        if cfg.get("JENEFAR_REQUIRE_EXPLICIT_APPROVAL_SECRET", "").strip().lower() in {"1", "true", "yes"}:
            failures.append("JENEFAR_APPROVAL_SECRET is required but not configured")
        else:
            warnings.append("approval secret not explicitly configured; process-local secret will be generated")
    if cfg.get("JENEFAR_TASK_HISTORY_PATH", "").startswith("/"):
        warnings.append("task history uses an absolute path; verify filesystem permissions")

    host = cfg.get("JENEFAR_HOST", "127.0.0.1").strip()
    loopback = host in {"127.0.0.1", "::1", "localhost"}
    auth_user = cfg.get("JENEFAR_AUTH_USER", "").strip()
    auth_password = cfg.get("JENEFAR_AUTH_PASSWORD", "")
    tls_cert = cfg.get("JENEFAR_TLS_CERT", "").strip()
    tls_key = cfg.get("JENEFAR_TLS_KEY", "").strip()
    allow_insecure_remote = cfg.get("JENEFAR_ALLOW_INSECURE_REMOTE", "").strip().lower() in {"1", "true", "yes"}

    if not loopback:
        if not auth_user or not auth_password:
            failures.append("remote deployment requires JENEFAR_AUTH_USER and JENEFAR_AUTH_PASSWORD")
        if not (tls_cert and tls_key) and not allow_insecure_remote:
            failures.append("remote deployment requires TLS certificate/key")
        if allow_insecure_remote:
            warnings.append("remote HTTP is explicitly allowed without TLS; use only behind a trusted TLS proxy")
    elif bool(tls_cert) != bool(tls_key):
        failures.append("JENEFAR_TLS_CERT and JENEFAR_TLS_KEY must be configured together")

    for label, path in (("TLS certificate", tls_cert), ("TLS private key", tls_key)):
        if path and not Path(path).expanduser().is_file():
            failures.append(f"{label} file does not exist")
    return {
        "ready": not failures,
        "providers": providers,
        "local_llm_configured": local_llm_configured,
        "failures": failures,
        "warnings": warnings,
    }
