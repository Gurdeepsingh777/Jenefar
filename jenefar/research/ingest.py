from __future__ import annotations

from jenefar.memory.chunker import chunk_text
from jenefar.memory.store import MemoryStore
from jenefar.research.sources import ResearchDocument

def ingest_research_document(
    document: ResearchDocument,
    store: MemoryStore,
    *,
    max_chars: int = 1200,
) -> int:
    chunks = chunk_text(document.content, max_chars=max_chars)
    added = 0
    for index, chunk in enumerate(chunks, start=1):
        title = f"{document.title} [chunk {index}/{len(chunks)}]"
        if store.add_document(source=document.source, title=title, content=chunk):
            added += 1
    return added

def ingest_research_documents(
    documents: list[ResearchDocument],
    store: MemoryStore,
    *,
    max_chars: int = 1200,
) -> int:
    return sum(
        ingest_research_document(document, store, max_chars=max_chars)
        for document in documents
    )

def index_url(url: str, store: MemoryStore) -> int:
    from jenefar.research.sources import fetch_url
    return ingest_research_document(fetch_url(url), store)

def index_github(
    repository: str,
    store: MemoryStore,
    *,
    ref: str = "main",
    paths: list[str] | None = None,
    max_files: int = 40,
) -> int:
    from jenefar.research.sources import fetch_github_repository
    docs = fetch_github_repository(repository, ref=ref, paths=paths, max_files=max_files)
    return ingest_research_documents(docs, store)
