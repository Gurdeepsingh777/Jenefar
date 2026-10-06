#!/usr/bin/env python3
"""Create a consistent backup of Jenefar's persistent local state."""
from __future__ import annotations
import os, tarfile, time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = root / os.getenv("JENEFAR_DATA_DIR", "data")
out_dir = root / "backups"
out_dir.mkdir(mode=0o700, exist_ok=True)
stamp = time.strftime("%Y%m%d-%H%M%S")
target = out_dir / f"jenefar-state-{stamp}.tar.gz"
patterns = ("*.jsonl", "*.db", "*.sqlite", "*.sqlite3", "*.json")
with tarfile.open(target, "w:gz") as archive:
    for path in data.rglob("*"):
        if path.is_file() and path.suffix in {".jsonl", ".db", ".sqlite", ".sqlite3", ".json"}:
            archive.add(path, arcname=path.relative_to(root))
os.chmod(target, 0o600)
print(target)
