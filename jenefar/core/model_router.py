from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSelection:
    role: str
    model: str
    source: str


class ModelRouter:
    """Select a configured model profile without hard-coding provider-specific names."""

    ROLE_ENV = {
        "fast": "JENEFAR_MODEL_FAST",
        "reasoning": "JENEFAR_MODEL_REASONING",
        "coding": "JENEFAR_MODEL_CODING",
        "security": "JENEFAR_MODEL_SECURITY",
        "research": "JENEFAR_MODEL_RESEARCH",
        "robotics": "JENEFAR_MODEL_ROBOTICS",
        "automation": "JENEFAR_MODEL_AUTOMATION",
        "vision": "JENEFAR_MODEL_VISION",
    }

    AGENT_ROLES = {
        "local_development": "coding",
        "python": "coding",
        "repository": "coding",
        "kali": "security",
        "cybersecurity": "security",
        "bugbounty": "security",
        "research": "research",
        "robotics": "robotics",
        "automation": "automation",
        "gui_vision": "vision",
        "utility": "fast",
    }

    def role_for_agent(self, agent_name: str) -> str:
        return self.AGENT_ROLES.get(agent_name, "fast")

    def role_for_intent(self, intent: str, agent_name: str | None = None) -> str:
        if agent_name:
            return self.role_for_agent(agent_name)
        return "fast"

    def resolve(self, role: str = "fast", *, explicit_model: str | None = None) -> ModelSelection:
        normalized = (role or "fast").strip().lower() or "fast"
        if explicit_model:
            return ModelSelection(normalized, explicit_model, "explicit-agent-model")
        role_env = self.ROLE_ENV.get(normalized)
        if role_env:
            configured = os.getenv(role_env, "").strip()
            if configured:
                return ModelSelection(normalized, configured, role_env)

        # The Telegram runtime uses generic OpenAI-compatible variables. When
        # those point to Google's endpoint, make the desktop/avatar runtime use
        # the same Gemini model instead of the OpenAI-only default model name.
        base_url = (
            os.getenv("LLM_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
        ).lower()
        if "generativelanguage.googleapis.com" in base_url:
            compatible_model = (
                os.getenv("LLM_MODEL_NAME", "").strip()
                or os.getenv("GEMINI_MODEL", "").strip()
            )
            if compatible_model:
                return ModelSelection(
                    normalized, compatible_model, "LLM_MODEL_NAME/GEMINI_MODEL"
                )

        default = os.getenv("OPENAI_MODEL", "").strip() or "gpt-5.6-luna"
        return ModelSelection(normalized, default, "OPENAI_MODEL/default")

    def local_model_env(self, role: str) -> str:
        return f"JENEFAR_LOCAL_LLM_MODEL_{(role or 'fast').strip().upper()}"


__all__ = ["ModelSelection", "ModelRouter"]
