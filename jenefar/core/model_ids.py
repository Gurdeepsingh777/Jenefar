"""Canonical model identifiers shared by routing, UI selection, and provider discovery."""
from __future__ import annotations


def normalize_model_id(model: str, provider: str | None = None) -> str:
    value = str(model or "").strip()
    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider == "gemini":
        if value.startswith("models/"):
            value = value[len("models/"):]
        # The public Gemini model ID includes the preview suffix. Normalize the
        # common shortened spelling seen in older local .env files.
        if value == "gemini-3.1-pro":
            value = "gemini-3.1-pro-preview"
    return value


__all__ = ["normalize_model_id"]
