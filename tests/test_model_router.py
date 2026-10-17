from jenefar.core.model_router import ModelRouter


def test_model_router_maps_specialists_to_roles():
    router = ModelRouter()
    assert router.role_for_agent("local_development") == "coding"
    assert router.role_for_agent("kali") == "security"
    assert router.role_for_agent("research") == "research"


def test_model_router_uses_role_environment(monkeypatch):
    monkeypatch.setenv("JENEFAR_MODEL_CODING", "test-coding-model")
    selected = ModelRouter().resolve("coding")
    assert selected.model == "test-coding-model"
    assert selected.source == "JENEFAR_MODEL_CODING"


def test_model_router_explicit_model_wins(monkeypatch):
    monkeypatch.setenv("JENEFAR_MODEL_CODING", "test-coding-model")
    selected = ModelRouter().resolve("coding", explicit_model="agent-specific")
    assert selected.model == "agent-specific"
    assert selected.source == "explicit-agent-model"


def test_google_compatible_runtime_uses_telegram_llm_model(monkeypatch):
    monkeypatch.setenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    monkeypatch.setenv("LLM_MODEL_NAME", "gemini-3.8-flash")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("JENEFAR_MODEL_FAST", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    selected = ModelRouter().resolve("fast")
    assert selected.model == "gemini-3.8-flash"
    assert selected.source == "LLM_MODEL_NAME/GEMINI_MODEL"


def test_role_environment_overrides_google_compatible_model(monkeypatch):
    monkeypatch.setenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    monkeypatch.setenv("LLM_MODEL_NAME", "gemini-default")
    monkeypatch.setenv("JENEFAR_MODEL_FAST", "role-specific-model")

    selected = ModelRouter().resolve("fast")
    assert selected.model == "role-specific-model"
    assert selected.source == "JENEFAR_MODEL_FAST"
