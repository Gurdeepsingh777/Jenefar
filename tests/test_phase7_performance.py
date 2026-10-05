from jenefar.core.provider_pool import ProviderPool


def test_adaptive_routing_keeps_configured_order_during_warmup(monkeypatch):
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openai,groq,gemini")
    monkeypatch.setenv("JENEFAR_ROUTING_WARMUP_SAMPLES", "2")
    pool = ProviderPool()
    assert pool.order_for_role("fast") == ["openai", "groq", "gemini"]


def test_adaptive_routing_prefers_faster_provider_after_warmup(monkeypatch):
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openai,groq,gemini")
    monkeypatch.setenv("JENEFAR_ROUTING_WARMUP_SAMPLES", "2")
    pool = ProviderPool()
    pool.record_latency("openai", 0.9, success=True)
    pool.record_latency("openai", 0.8, success=True)
    pool.record_latency("groq", 0.1, success=True)
    pool.record_latency("groq", 0.2, success=True)
    assert pool.order_for_role("fast")[0] == "groq"


def test_adaptive_routing_can_be_disabled(monkeypatch):
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openai,groq")
    monkeypatch.setenv("JENEFAR_ADAPTIVE_ROUTING", "0")
    pool = ProviderPool()
    pool.record_latency("groq", 0.01, success=True)
    assert pool.order_for_role("fast") == ["openai", "groq"]


def test_provider_status_exposes_latency(monkeypatch):
    monkeypatch.setenv("JENEFAR_PROVIDER_ORDER", "openai")
    pool = ProviderPool()
    pool.record_latency("openai", 0.1234, success=True)
    status = pool.status("fast")["openai"]["latency"]
    assert status["samples"] == 1
    assert status["average_ms"] == 123.4


def test_latency_summary_reports_percentiles(tmp_path):
    from jenefar.evaluation.trace import ExecutionTrace, TraceStore
    store = TraceStore(tmp_path / "traces.jsonl")
    for value in (100, 200, 300, 1000):
        trace = ExecutionTrace(status="success", started_at=0.0, finished_at=value / 1000.0)
        store.append(trace)
    summary = store.summary()
    assert summary["p50_elapsed_ms"] == 200
    assert summary["p95_elapsed_ms"] == 1000
    assert summary["max_elapsed_ms"] == 1000
