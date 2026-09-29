from pathlib import Path
import json

from jenefar.execution.audit import AuditLogger

def test_audit_writes_jsonl(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    AuditLogger(path).record("test_event", ok=True)
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert entry["event"] == "test_event"
    assert entry["ok"] is True
