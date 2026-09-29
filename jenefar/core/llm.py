from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass
class LLMResponse:
    text: str
    provider: str = "local"

class LLMClient:
    """Provider boundary. OpenAI-compatible implementation is optional."""
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.6")

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def complete(self, prompt: str) -> LLMResponse:
        if not self.available():
            return LLMResponse(
                "LLM provider is not configured yet. Set OPENAI_API_KEY in .env.",
                "unconfigured",
            )
        # Network provider is intentionally isolated here; routing/tool execution
        # remains deterministic and auditable.
        return LLMResponse(
            f"LLM request prepared for model {self.model}: {prompt}",
            "openai-compatible",
        )
