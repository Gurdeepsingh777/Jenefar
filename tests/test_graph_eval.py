from pathlib import Path

from jenefar.evaluation.loop import EvaluationLoop
from jenefar.memory.graph import KnowledgeGraph


def test_graph_learns_relations(tmp_path: Path):
    graph = KnowledgeGraph(tmp_path / "memory.db")
    relations = graph.learn_text("Jenefar uses Python")
    assert relations
    assert relations[0].predicate == "uses"


def test_graph_search(tmp_path: Path):
    graph = KnowledgeGraph(tmp_path / "memory.db")
    graph.add_relation("Jenefar", "uses", "Python")
    hits = graph.search("Jenefar")
    assert hits[0].object == "Python"


def test_evaluation_records_quality(tmp_path: Path):
    loop = EvaluationLoop(tmp_path / "eval.jsonl")
    result = loop.evaluate("hello", "hello back", provider="openai")
    assert result.passed
    assert loop.recent(1)[0]["score"] == result.score
