from __future__ import annotations

from jenefar.execution.task_graph import TaskGraph, TaskNode


def test_completed_task_graph_nodes_resume_from_checkpoint(tmp_path):
    checkpoint = tmp_path / "graph-checkpoint.json"
    first_calls = []
    first = TaskGraph(checkpoint)
    first.add(TaskNode("prepare", lambda _: first_calls.append("prepare") or {"ready": True}))
    first.add(TaskNode("run", lambda _: first_calls.append("run") or "done", deps={"prepare"}))
    result = first.run()
    assert result["prepare"].state == "completed"
    assert result["run"].state == "completed"
    assert first_calls == ["prepare", "run"]

    resumed_calls = []
    resumed = TaskGraph(checkpoint)
    resumed.add(TaskNode("prepare", lambda _: resumed_calls.append("prepare") or {"ready": False}))
    resumed.add(TaskNode("run", lambda _: resumed_calls.append("run") or "rerun", deps={"prepare"}))
    resumed.add(TaskNode("verify", lambda _: resumed_calls.append("verify") or "verified", deps={"run"}))
    result = resumed.run()

    assert result["prepare"].state == "completed"
    assert result["run"].state == "completed"
    assert result["verify"].state == "completed"
    assert resumed_calls == ["verify"]


def test_task_graph_rejects_unbounded_or_nonfinite_configuration():
    graph = TaskGraph()
    graph.add(TaskNode("bounded", lambda _: True, timeout=9999, retries=99))
    assert graph.nodes["bounded"].timeout == 300
    assert graph.nodes["bounded"].retries == 3
    try:
        graph.add(TaskNode("nan", lambda _: None, timeout=float("nan")))
    except ValueError:
        pass
    else:
        raise AssertionError("non-finite timeout should be rejected")
