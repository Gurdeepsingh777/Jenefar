from __future__ import annotations

from typing import Any

import httpx

from config import Settings


class LLMError(RuntimeError):
    """A provider/API error safe to summarize to the Telegram user."""


class LLMRateLimitError(LLMError):
    """The provider rate-limited the current request."""


class OpenAICompatibleLLM:
    """Minimal asynchronous Chat Completions client for OpenAI-compatible APIs.

    Configure LLM_API_KEY, LLM_BASE_URL and LLM_MODEL_NAME. The base URL normally
    includes the provider's /v1 prefix, e.g. https://api.groq.com/openai/v1.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.llm_model_name,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"

        try:
            response = await self.client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMError("The LLM provider timed out. Please retry the request.") from exc
        except httpx.RequestError as exc:
            raise LLMError(
                f"Could not connect to the LLM provider ({type(exc).__name__}). Check BASE_URL and network connectivity."
            ) from exc

        if response.status_code == 429:
            raise LLMRateLimitError(
                "The LLM provider rate limit was reached. Wait briefly or try a provider with more free quota."
            )
        if response.status_code in {401, 403}:
            raise LLMError(
                f"The LLM provider rejected the API credentials (HTTP {response.status_code}). Check LLM_API_KEY."
            )
        if response.status_code >= 500:
            raise LLMError(
                f"The LLM provider is temporarily unavailable (HTTP {response.status_code}). Please retry."
            )
        if not response.is_success:
            detail = ""
            try:
                data = response.json()
                detail = str((data.get("error") or {}).get("message") or data.get("message") or "")
            except (ValueError, AttributeError):
                detail = ""
            detail = detail.strip().replace("\n", " ")[:500]
            suffix = f": {detail}" if detail else ""
            raise LLMError(f"LLM request failed with HTTP {response.status_code}{suffix}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("The LLM provider returned invalid JSON.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("choices"), list) or not data["choices"]:
            raise LLMError("The LLM provider response did not contain a completion.")
        return data

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()
