from __future__ import annotations

from jenefar.core.production_runtime import ProductionRuntime


def test_production_runtime_task_metrics_and_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("JENEFAR_TASK_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.chdir(tmp_path)
    runtime = ProductionRuntime()
    runtime.task_started("t1", "safe test", agent="utility")
    runtime.remember("production runtime integration", importance=0.8)
    runtime.task_finished("t1", state="completed", agent="utility", provider="local")
    snapshot = runtime.snapshot()
    assert snapshot["metrics"]["counters"]["tasks_started"] == 1
    assert snapshot["metrics"]["counters"]["tasks_completed"] == 1
    assert snapshot["memory"]["count"] == 1
    assert (tmp_path / "data" / "security_audit.jsonl").exists()


def test_production_runtime_task_graph_factory():
    runtime = ProductionRuntime()
    graph = runtime.build_task_graph()
    assert graph.nodes == {}


def test_production_runtime_voice_and_readiness():
    runtime = ProductionRuntime()
    turn = runtime.voice.begin("voice-1", "hello")
    assert runtime.voice.active is turn
    assert "ready" in runtime.readiness()
