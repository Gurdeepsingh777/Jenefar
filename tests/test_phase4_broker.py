from pathlib import Path

from jenefar.events.engine import EventEngine
from jenefar.execution.audit import AuditLogger
from jenefar.memory.advanced import AdvancedMemory
from jenefar.memory.store import MemoryStore
from jenefar.tools.broker import ToolBroker


class NoEmbedding:
    def encode(self, _text):
        return None


def test_phase4_tools_and_headless_backend(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JENEFAR_DESKTOP_BACKEND", "headless")
    memory = AdvancedMemory(
        MemoryStore(tmp_path / "memory.db"),
        embedder=NoEmbedding(),
    )
    events = EventEngine(tmp_path / "events.db")
    broker = ToolBroker(
        require_confirmation=False,
        audit=AuditLogger(tmp_path / "audit.jsonl"),
        memory=memory,
        events=events,
    )

    assert broker.desktop.__class__.__name__ == "HeadlessDesktopAutomation"
    names = {spec.name for spec in broker.registry.list()}
    assert {"memory_recall", "memory_remember", "event_catalog", "event_schedule_once", "event_watch"} <= names

    recall = broker.invoke(
        "memory_recall",
        {"query": "nothing stored yet", "limit": 3, "layers": []},
    )
    assert '"status": "ok"' in recall

    created = broker.invoke(
        "event_schedule_once",
        {
            "name": "phase4-test",
            "prompt": "safe test",
            "run_at": "2030-01-01T00:00:00+00:00",
        },
    )
    assert '"phase4-test"' in created
