from pathlib import Path

from jenefar.capabilities.store import CapabilityStore


def test_capability_store_persists(tmp_path: Path):
    store = CapabilityStore(tmp_path / "capabilities.json")
    item = store.add("Local video-call feature development", "User requested automatic file edits.")
    assert item["capability"] == "Local video-call feature development"
    assert store.list()[0]["notes"].startswith("User requested")
