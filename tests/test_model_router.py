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
