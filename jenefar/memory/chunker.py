from __future__ import annotations

def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    clean = " ".join(text.split()).strip()
    if not clean:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be >= 0 and < max_chars")

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + max_chars)
        if end < len(clean):
            boundary = clean.rfind(" ", start, end)
            if boundary > start + max_chars // 2:
                end = boundary
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean):
            break
        start = max(0, end - overlap)
    return chunks
