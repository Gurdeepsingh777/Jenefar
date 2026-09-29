from __future__ import annotations

from pathlib import Path

from jenefar.memory.chunker import chunk_text
from jenefar.memory.store import MemoryStore

TEXT_EXTENSIONS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".toml", ".csv", ".log"}

def ingest_file(path: str | Path, store: MemoryStore, *, max_chars: int = 1200) -> int:
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(file)
    if file.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError(f"Unsupported text extension: {file.suffix}")

    content = file.read_text(encoding="utf-8", errors="ignore")
    chunks = chunk_text(content, max_chars=max_chars)
    added = 0
    for index, chunk in enumerate(chunks, start=1):
        title = f"{file.name} [chunk {index}/{len(chunks)}]"
        if store.add_document(source=str(file), title=title, content=chunk):
            added += 1
    return added

def ingest_directory(path: str | Path, store: MemoryStore) -> int:
    root = Path(path)
    if not root.is_dir():
        raise NotADirectoryError(root)
    total = 0
    for file in sorted(root.rglob("*")):
        if file.is_file() and file.suffix.lower() in TEXT_EXTENSIONS:
            try:
                total += ingest_file(file, store)
            except (UnicodeError, OSError):
                continue
    return total
