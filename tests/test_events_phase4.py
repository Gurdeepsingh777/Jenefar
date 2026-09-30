from datetime import datetime, timedelta, timezone
from pathlib import Path

from jenefar.events.engine import EventEngine


def test_once_event_runs_and_disables(tmp_path: Path):
    engine = EventEngine(tmp_path / "events.db")
    run_at = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    event = engine.schedule_once("one", "do a safe test", run_at)

    calls = []
    now = datetime(2030, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    result = engine.run_due(lambda prompt, item: calls.append((prompt, item.name)) or "ok", now=now)

    assert result[0]["status"] == "ok"
    assert calls == [("do a safe test", "one")]
    assert engine.list(include_disabled=False) == []
    assert engine.list()[0].run_count == 1


def test_interval_and_event_watch(tmp_path: Path):
    engine = EventEngine(tmp_path / "events.db")
    start = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    engine.schedule_interval("poll", "poll once", 60, start_at=start)
    engine.watch("download", "download.finished", "summarize", filters={"path": "a.zip"})

    now = datetime(2030, 1, 1, 0, 1, 1, tzinfo=timezone.utc)
    due = engine.due(now)
    assert [item.name for item in due] == ["poll"]

    matched = engine.emit("download.finished", {"path": "a.zip", "size": 10}, now=now)
    assert [item.name for item in matched] == ["download"]

    queued = engine.due(now)
    assert [item.name for item in queued] == ["download"]

    calls = []
    result = engine.run_due(lambda prompt, item: calls.append(prompt) or "queued", now=now)
    assert result[0]["status"] == "ok"
    assert calls == ["summarize"]
    assert engine.list(include_disabled=False)[0].name == "poll"
