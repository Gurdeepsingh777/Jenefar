from pathlib import Path

from jenefar.memory.graph import KnowledgeGraph
from jenefar.memory.semantic import SemanticEmbedder


def test_semantic_cosine_identity():
    assert SemanticEmbedder.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_graph_persists_with_embedding_column(tmp_path: Path):
    graph = KnowledgeGraph(tmp_path / "memory.db", embedder=SemanticEmbedder())
    graph.add_relation("Jenefar", "uses", "Python")
    assert graph.search("Jenefar")
