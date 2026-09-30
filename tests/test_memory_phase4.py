from datetime import datetime, timedelta, timezone
from pathlib import Path

from jenefar.memory.advanced import AdvancedMemory
from jenefar.memory.semantic import SemanticEmbedder
from jenefar.memory.store import MemoryStore


class NoEmbedding:
    def encode(self, _text):
        return None


def test_layered_memory_retrieval_and_procedure(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.db")
    memory = AdvancedMemory(store, embedder=NoEmbedding())

    memory.record_episode(
        title="ESP32 session",
        content="ESP32 servo calibration and serial monitor workflow",
        source="conversation",
        importance=0.8,
    )
    memory.remember_fact(
        title="Preferred robot workflow",
        content="Use serial monitor before changing the servo code.",
        importance=0.95,
        tags=["robotics"],
    )
    memory.save_procedure(
        name="servo debug",
        trigger_text="debug esp32 servo",
        steps=["inspect wiring", "open serial monitor", "test servo angle"],
        constraints=["authorized hardware only"],
    )

    recall = memory.recall("ESP32 servo", limit=10)
    assert recall.hits
    assert any(hit.layer == "semantic" for hit in recall.hits)
    assert recall.procedures[0]["name"] == "servo debug"


def test_memory_expiry_is_safe(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.db")
    memory = AdvancedMemory(store, embedder=NoEmbedding())
    memory.record_episode(
        title="temporary",
        content="expire this record",
        source="test",
        ttl_seconds=1,
    )
    assert memory.purge_expired() == 0

    with memory._connect() as con:
        con.execute(
            "UPDATE memory_items SET created_at = ? WHERE title = ?",
            ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(), "temporary"),
        )

    assert memory.purge_expired() == 1
