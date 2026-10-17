"""Provider-backed model discovery for the local dashboard.

Live catalog results are preferred. A small documented fallback catalog is used
only when a provider's discovery endpoint is unreachable.
"""
from __future__ import annotations

import httpx

from jenefar.core.model_ids import normalize_model_id
from jenefar.core.provider_pool import ProviderPool


FALLBACK_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-pro-preview",
    ],
    "openai": [],
    "openrouter": ["openrouter/free"],
    "groq": ["openai/gpt-oss-120b"],
    "cerebras": ["gpt-oss-120b"],
}


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def list_provider_models(provider: str, pool: ProviderPool | None = None) -> dict:
    """Return model IDs available from the selected provider or a clear fallback."""
    pool = pool or ProviderPool()
    name = str(provider or "").strip().lower()
    if name not in pool.CONFIGS:
        raise ValueError("Unknown model provider.")
    if not pool.configured(name):
        return {"provider": name, "models": [], "source": "not-configured"}

    key = pool.api_key(name)
    config = pool.CONFIGS[name]
    try:
        timeout = httpx.Timeout(4.0, connect=2.0)
        if name == "gemini":
            response = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            models: list[str] = []
            for item in payload.get("models", []):
                if not isinstance(item, dict):
                    continue
                methods = item.get("supportedGenerationMethods", [])
                model_id = normalize_model_id(str(item.get("name", "")), "gemini")
                lowered = model_id.lower()
                if (
                    "generateContent" in methods
                    and model_id.startswith(("gemini-", "gemma-"))
                    and not any(marker in lowered for marker in (
                        "-image", "-tts", "transcribe", "-live", "embedding", "robotics"
                    ))
                ):
                    models.append(model_id)
        else:
            base_url = config.base_url.rstrip("/") if config.base_url else "https://api.openai.com/v1"
            response = httpx.get(
                base_url + "/models",
                headers={"Authorization": "Bearer " + key},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            records = payload.get("data", [])
            models = [
                str(item.get("id", "")).strip()
                for item in records
                if isinstance(item, dict) and str(item.get("id", "")).strip()
            ]
        models = sorted(set(models), key=str.casefold)
        if models:
            # Keep the most frequently selected, currently configured model easy to find.
            configured = normalize_model_id(pool.model(name, "fast"), name)
            if configured in models:
                models.remove(configured)
                models.insert(0, configured)
            return {"provider": name, "models": models[:150], "source": "provider-api"}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        failure = f"{type(exc).__name__}: {exc}"
    else:
        failure = "The provider returned no compatible chat models."

    configured = normalize_model_id(pool.model(name, "fast"), name)
    fallback = _unique([configured, *FALLBACK_MODELS.get(name, [])])
    return {
        "provider": name,
        "models": fallback,
        "source": "fallback",
        "diagnostic": failure,
    }


__all__ = ["FALLBACK_MODELS", "list_provider_models"]
