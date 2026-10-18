from __future__ import annotations
import concurrent.futures
import json
import time

def test_memory_v2_persists_and_forgets(tmp_path, monkeypatch):
    monkeypatch.setenv("JENEFAR_MEMORY_V2_PATH", str(tmp_path / "memory.jsonl"))
    from jenefar.memory.manager_v2 import MemoryManagerV2
    first = MemoryManagerV2()
    record = first.upsert("persistent production memory", kind="semantic", importance=0.9)
    second = MemoryManagerV2()
    assert second.search("production memory", 1)[0].memory_id == record.memory_id
    assert second.forget(record.memory_id)
    assert not MemoryManagerV2().records

def test_audit_chain_concurrent_appends(tmp_path):
    from jenefar.security.policy import AuditChain
    chain = AuditChain(tmp_path / "audit.jsonl")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: chain.append({"event": f"event-{i}"}), range(32)))
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert len(lines) == 32
    previous = ""
    for line in lines:
        item = json.loads(line)
        assert item["previous_hash"] == previous
        previous = item["hash"]

def test_security_url_boundary():
    from jenefar.security.policy import validate_url
    assert validate_url("https://example.com/path").startswith("https://example.com")
    for url in ("http://127.0.0.1:11434", "http://localhost", "file:///etc/passwd"):
        try:
            validate_url(url)
        except (ValueError, PermissionError):
            pass
        else:
            raise AssertionError(f"unsafe URL accepted: {url}")

def test_task_graph_parallel_runtime():
    from jenefar.execution.task_graph import TaskGraph, TaskNode
    graph = TaskGraph()
    graph.add(TaskNode("a", lambda _: (time.sleep(0.03), "a")[1], timeout=1))
    graph.add(TaskNode("b", lambda _: (time.sleep(0.03), "b")[1], timeout=1))
    started = time.monotonic()
    result = graph.run(max_workers=2)
    elapsed = time.monotonic() - started
    assert all(item.state == "completed" for item in result.values())
    assert elapsed < 0.15

def test_ui_runtime_contract():
    from pathlib import Path
    app = Path("jenefar/avatar/web/app.js").read_text()
    html = Path("jenefar/avatar/web/index.html").read_text()
    assert "/runtime/status" in app and "/runtime/tasks" in app
    assert "runtime-intel" in html and "task-history" in html
