from __future__ import annotations

import os
from dataclasses import dataclass

@dataclass
class LLMResponse:
    text: str
    provider: str = "local"
    response_id: str | None = None

class LLMClient:
    """OpenAI Responses API boundary with optional hosted web search."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        self._client = None

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def _client_or_raise(self):
        if not self.available():
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        instructions: str = "You are Jenefar, a precise and helpful multi-agent assistant.",
        use_web_search: bool = False,
        safety_identifier: str | None = None,
    ) -> LLMResponse:
        if not self.available():
            return LLMResponse(
                "LLM provider is not configured. Set OPENAI_API_KEY in .env.",
                "unconfigured",
            )

        client = self._client_or_raise()
        kwargs = {
            "model": self.model,
            "instructions": instructions,
            "input": prompt,
            "store": False,
        }
        if safety_identifier:
            kwargs["safety_identifier"] = safety_identifier
        if use_web_search:
            kwargs["tools"] = [{"type": "web_search"}]

        try:
            response = client.responses.create(**kwargs)
        except Exception as exc:
            return LLMResponse(
                f"LLM request failed: {type(exc).__name__}: {exc}",
                "error",
            )

        return LLMResponse(
            text=response.output_text or "The model returned no text.",
            provider="openai",
            response_id=getattr(response, "id", None),
        )
