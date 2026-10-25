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


def test_simple_complexity_uses_fast_role(monkeypatch):
    monkeypatch.setenv("JENEFAR_MODEL_FAST", "fast-model")
    monkeypatch.setenv("JENEFAR_MODEL_CODING", "coding-model")
    router = ModelRouter()
    assert router.role_for_complexity("local_development", "simple") == "fast"
    selected = router.resolve("coding", complexity="simple")
    assert selected.role == "fast"
    assert selected.model == "fast-model"


def test_hard_coding_prefers_coding_model(monkeypatch):
    monkeypatch.setenv("JENEFAR_MODEL_CODING", "coding-model")
    monkeypatch.setenv("JENEFAR_MODEL_REASONING", "reason-model")
    router = ModelRouter()
    assert router.role_for_complexity("local_development", "hard") == "coding"
    selected = router.resolve("coding", complexity="hard")
    assert selected.role == "coding"
    assert selected.model == "coding-model"


def test_hard_non_coding_uses_reasoning_when_configured(monkeypatch):
    monkeypatch.setenv("JENEFAR_MODEL_REASONING", "reason-model")
    monkeypatch.setenv("JENEFAR_MODEL_RESEARCH", "research-model")
    router = ModelRouter()
    assert router.role_for_complexity("research", "hard") == "reasoning"
    selected = router.resolve("research", complexity="hard")
    assert selected.role == "reasoning"
    assert selected.model == "reason-model"


def test_hard_without_reasoning_keeps_agent_role(monkeypatch):
    monkeypatch.delenv("JENEFAR_MODEL_REASONING", raising=False)
    monkeypatch.setenv("JENEFAR_MODEL_RESEARCH", "research-model")
    router = ModelRouter()
    assert router.role_for_complexity("research", "hard") == "research"
    selected = router.resolve("research", complexity="hard")
    assert selected.role == "research"
    assert selected.model == "research-model"
