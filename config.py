from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

# Local .env is convenient for bare-metal runs; environment values always win.
load_dotenv(override=False)


class ConfigurationError(ValueError):
    """Raised when required Telegram agent configuration is missing or invalid."""


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def _parse_allowed_ids(raw: str) -> frozenset[int]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise ConfigurationError(
            "Set ALLOWED_TELEGRAM_USER_IDS to your numeric Telegram user ID(s), comma-separated."
        )
    result: set[int] = set()
    for value in values:
        try:
            identifier = int(value)
        except ValueError as exc:
            raise ConfigurationError(
                "ALLOWED_TELEGRAM_USER_IDS must contain only comma-separated integers."
            ) from exc
        if identifier <= 0:
            raise ConfigurationError("Telegram user IDs must be positive integers.")
        result.add(identifier)
    if not result:
        raise ConfigurationError("At least one authorized Telegram user ID is required.")
    return frozenset(result)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_telegram_user_ids: frozenset[int]
    llm_api_key: str
    llm_base_url: str
    llm_model_name: str
    github_pat: str = ""
    github_api_url: str = "https://api.github.com"
    scratchpad_dir: Path = Path("data/scratchpad")
    skill_store_dir: Path = Path("data/skills")
    request_timeout_seconds: float = 30.0
    agent_timeout_seconds: float = 180.0
    max_tool_rounds: int = 8
    max_history_messages: int = 24
    max_input_chars: int = 12000
    max_tool_output_chars: int = 12000

    @classmethod
    def from_env(cls) -> "Settings":
        token = _first_env("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required.")

        allowed_ids = _parse_allowed_ids(_first_env("ALLOWED_TELEGRAM_USER_IDS"))

        # Generic names are supported as requested; provider-specific aliases make
        # Groq/OpenRouter/Gemini-compatible endpoints easy to configure.
        api_key = _first_env(
            "LLM_API_KEY",
            "API_KEY",
            "GROQ_API_KEY",
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
        )
        if not api_key:
            raise ConfigurationError(
                "Set LLM_API_KEY (or API_KEY / a supported provider-specific API key)."
            )

        base_url = _first_env(
            "LLM_BASE_URL",
            "BASE_URL",
            default="https://api.groq.com/openai/v1",
        ).rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("LLM_BASE_URL must be a valid HTTP(S) API base URL.")
        if parsed.username or parsed.password:
            raise ConfigurationError("Do not put credentials in LLM_BASE_URL; use LLM_API_KEY.")

        model = _first_env(
            "LLM_MODEL_NAME",
            "MODEL_NAME",
            "GROQ_MODEL",
            "OPENROUTER_MODEL",
            "GEMINI_MODEL",
            "OPENAI_MODEL",
            default="openai/gpt-oss-120b",
        )
        github_pat = _first_env("GITHUB_PAT", "GITHUB_TOKEN")
        github_api_url = _first_env("GITHUB_API_URL", default="https://api.github.com").rstrip("/")
        github_url = urlsplit(github_api_url)
        if github_url.scheme not in {"http", "https"} or not github_url.netloc:
            raise ConfigurationError("GITHUB_API_URL must be a valid HTTP(S) URL.")

        try:
            request_timeout = float(_first_env("REQUEST_TIMEOUT_SECONDS", default="30"))
            agent_timeout = float(_first_env("AGENT_TIMEOUT_SECONDS", default="180"))
            rounds = int(_first_env("MAX_TOOL_ROUNDS", default="8"))
            history = int(_first_env("MAX_HISTORY_MESSAGES", default="24"))
            input_chars = int(_first_env("MAX_INPUT_CHARS", default="12000"))
            tool_chars = int(_first_env("MAX_TOOL_OUTPUT_CHARS", default="12000"))
        except ValueError as exc:
            raise ConfigurationError("Timeouts and limit settings must be numeric.") from exc

        if not (1 <= request_timeout <= 180):
            raise ConfigurationError("REQUEST_TIMEOUT_SECONDS must be between 1 and 180.")
        if not (5 <= agent_timeout <= 900):
            raise ConfigurationError("AGENT_TIMEOUT_SECONDS must be between 5 and 900.")
        if not (1 <= rounds <= 20):
            raise ConfigurationError("MAX_TOOL_ROUNDS must be between 1 and 20.")
        if not (4 <= history <= 100):
            raise ConfigurationError("MAX_HISTORY_MESSAGES must be between 4 and 100.")
        if not (100 <= input_chars <= 50000):
            raise ConfigurationError("MAX_INPUT_CHARS must be between 100 and 50000.")
        if not (1000 <= tool_chars <= 50000):
            raise ConfigurationError("MAX_TOOL_OUTPUT_CHARS must be between 1000 and 50000.")

        return cls(
            telegram_bot_token=token,
            allowed_telegram_user_ids=allowed_ids,
            llm_api_key=api_key,
            llm_base_url=base_url,
            llm_model_name=model,
            github_pat=github_pat,
            github_api_url=github_api_url,
            scratchpad_dir=Path(_first_env("SCRATCHPAD_DIR", default="data/scratchpad")).expanduser(),
            skill_store_dir=Path(_first_env("SKILL_STORE_DIR", default="data/skills")).expanduser(),
            request_timeout_seconds=request_timeout,
            agent_timeout_seconds=agent_timeout,
            max_tool_rounds=rounds,
            max_history_messages=history,
            max_input_chars=input_chars,
            max_tool_output_chars=tool_chars,
        )

    def is_authorized(self, telegram_user_id: int | None) -> bool:
        return telegram_user_id is not None and int(telegram_user_id) in self.allowed_telegram_user_ids
