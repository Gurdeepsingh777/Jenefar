from __future__ import annotations
import time
from pathlib import Path
import pytest

from jenefar.security.policy import ApprovalManager, safe_path, validate_url, redact, AuditChain
from jenefar.execution.task_graph import TaskGraph, TaskNode
from jenefar.memory.manager_v2 import MemoryManagerV2
from jenefar.tools.skill_runtime import SkillRuntime, SkillManifest
from jenefar.voice.session_v2 import VoiceSession
from jenefar.vision.grounding import GroundingEngine, VisualElement
from jenefar.observability.runtime_metrics import RuntimeMetrics
from jenefar.evaluation.benchmark import BenchmarkRunner, BenchmarkCase

def test_security_boundaries(tmp_path):
    root=tmp_path/"root"; root.mkdir()
    assert safe_path(root/"x", [root]).parent == root
    with pytest.raises(PermissionError): safe_path(tmp_path/"x", [root])
    with pytest.raises(PermissionError): validate_url("http://127.0.0.1")
    assert "[REDACTED]" in redact("api_key=supersecret")
    a=ApprovalManager("test-secret",ttl_seconds=30); token=a.issue("delete", "t1")
    assert a.verify(token,"delete","t1") and not a.verify(token,"other","t1")
    chain=AuditChain(tmp_path/"audit.jsonl"); h=chain.append({"event":"secret token=abc"}); assert len(h)==64

def test_task_graph_dependencies_and_parallelism(tmp_path):
    seen=[]
    g=TaskGraph(tmp_path/"checkpoint.json")
    g.add(TaskNode("a",lambda _: seen.append("a") or 1))
    g.add(TaskNode("b",lambda _: seen.append("b") or 2,deps={"a"}))
    g.add(TaskNode("c",lambda _: seen.append("c") or 3,deps={"a"}))
    r=g.run()
    assert all(v.state=="completed" for v in r.values()) and {"a","b","c"}==set(r)

def test_task_graph_cycle():
    g=TaskGraph(); g.add(TaskNode("a",lambda _:1,deps={"b"})); g.add(TaskNode("b",lambda _:1,deps={"a"}))
    with pytest.raises(ValueError): g.validate()

def test_memory_v2():
    m=MemoryManagerV2(); r=m.upsert("Python debugging workflow",importance=.9,provenance="test")
    assert m.search("Python debugging")[0].memory_id==r.memory_id
    assert m.forget(r.memory_id)

def test_skill_runtime():
    s=SkillRuntime(); s.register(SkillManifest("browser","1.0",permissions=frozenset({"browser"})))
    assert s.available("browser",{"browser"}); assert not s.available("browser",set())

def test_voice_interrupt():
    s=VoiceSession(); s.begin("1","hello"); x=s.begin("2","new"); assert x.turn_id=="2"; assert s.history[0].interrupted

def test_grounding():
    e=[VisualElement("1","button","Submit",0,0,100,40,.95),VisualElement("2","text","Cancel",0,50,100,40,.9)]
    assert GroundingEngine().require_confident(GroundingEngine().rank(e,"Submit","button")).element_id=="1"

def test_metrics():
    m=RuntimeMetrics(); m.inc("tasks"); m.observe("latency",2); m.record_llm(100,.01,.5)
    s=m.snapshot(); assert s["tokens"]==100 and s["cost_usd"]==.01

def test_benchmark():
    r=BenchmarkRunner().run([BenchmarkCase("1","x","ok")],lambda _: "ok")
    assert BenchmarkRunner.summary(r)["success_rate"]==1.0


def test_task_graph_node_timeout():
    import time
    from jenefar.execution.task_graph import TaskGraph, TaskNode
    graph = TaskGraph()
    graph.add(TaskNode("slow", lambda _: (time.sleep(0.05), "done")[1], timeout=0.01, retries=0))
    result = graph.run()["slow"]
    assert result.state == "failed"
    assert "timeout" in (result.error or "")


def test_orchestrator_exposes_production_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("JENEFAR_TASK_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.chdir(tmp_path)
    from jenefar.core.orchestrator import JenefarOrchestrator
    runtime = JenefarOrchestrator()
    snapshot = runtime.runtime_status()
    assert "production" in snapshot
    assert "metrics" in snapshot["production"]
    assert "memory" in snapshot["production"]
    assert "readiness" in snapshot["production"]
