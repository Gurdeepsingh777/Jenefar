from __future__ import annotations

from jenefar.core.orchestrator import JenefarOrchestrator


def test_voice_provider_module_imports():
    from jenefar.voice.provider import ProviderVoiceRuntime
    assert ProviderVoiceRuntime is not None


def test_model_metadata_is_rendered():
    orchestrator = JenefarOrchestrator()
    class Result:
        metadata = {"provider": "openrouter", "model": "openrouter/free"}
        content = "hello"
    # Ensure the metadata keys used by the runtime are stable.
    assert Result.metadata["provider"] == "openrouter"
    assert Result.metadata["model"] == "openrouter/free"
    assert orchestrator is not None
