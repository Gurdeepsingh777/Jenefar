from pathlib import Path

from jenefar.coding.repository import RepositoryPlan
from jenefar.docs.ingest import read_document
from jenefar.memory.store import MemoryStore
from jenefar.docs.ingest import ingest_document

def test_repository_plan_is_structured():
    plan = RepositoryPlan(
        repository="owner/repo",
        task="fix tests",
        likely_files=["tests/test_app.py"],
        checks=["pytest"],
        risks=["none"],
    )
    assert plan.likely_files

def test_text_document_ingest(tmp_path: Path):
    path = tmp_path / "notes.md"
    path.write_text("# Jenefar\nPython robotics memory", encoding="utf-8")
    store = MemoryStore(tmp_path / "memory.db")
    assert ingest_document(path, store) > 0
    assert store.search("robotics")[0].source == str(path)

def test_missing_document_fails():
    from pytest import raises
    with raises(FileNotFoundError):
        read_document("does-not-exist.pdf")
