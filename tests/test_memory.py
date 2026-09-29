from pathlib import Path

from jenefar.memory.chunker import chunk_text
from jenefar.memory.store import MemoryStore

def test_chunk_text_returns_overlapping_chunks():
    chunks = chunk_text("one two three four five six seven eight nine", max_chars=20, overlap=5)
    assert len(chunks) >= 2
    assert "one" in chunks[0]

def test_memory_persists_documents(tmp_path: Path):
    db = tmp_path / "memory.db"
    store = MemoryStore(db)
    assert store.add_document(source="test", title="Jenefar", content="Python robotics project") is True
    assert store.add_document(source="test", title="Jenefar", content="Python robotics project") is False

    hits = store.search("robotics")
    assert hits
    assert hits[0].title == "Jenefar"

def test_memory_persists_messages(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.db")
    store.remember_message("s1", "user", "remember my ESP32 project")
    assert store.recent_messages("s1")[0]["content"] == "remember my ESP32 project"
