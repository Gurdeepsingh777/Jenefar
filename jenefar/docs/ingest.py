from __future__ import annotations

from pathlib import Path
from typing import Callable

from jenefar.memory.chunker import chunk_text
from jenefar.memory.store import MemoryStore

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}

def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install pypdf to ingest PDF files.") from exc

    reader = PdfReader(str(path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {page_number}]\n{text}")
    return "\n\n".join(pages)

def _docx_text(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install python-docx to ingest DOCX files.") from exc

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

def read_document(path: str | Path) -> str:
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(file)
    suffix = file.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported document type: {suffix}")
    if suffix == ".pdf":
        return _pdf_text(file)
    if suffix == ".docx":
        return _docx_text(file)
    return file.read_text(encoding="utf-8", errors="ignore")

def ingest_document(path: str | Path, store: MemoryStore, *, max_chars: int = 1400) -> int:
    file = Path(path)
    content = read_document(file)
    chunks = chunk_text(content, max_chars=max_chars)
    added = 0
    for index, chunk in enumerate(chunks, start=1):
        title = f"{file.name} [chunk {index}/{len(chunks)}]"
        if store.add_document(source=str(file), title=title, content=chunk):
            added += 1
    return added
