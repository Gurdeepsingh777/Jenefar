from __future__ import annotations

import base64
import html
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_BYTES = 2_000_000
GITHUB_MAX_FILE_BYTES = 900_000
TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h",
    ".cpp", ".hpp", ".go", ".rs", ".rb", ".php", ".sh", ".bash", ".yaml",
    ".yml", ".json", ".toml", ".ini", ".cfg", ".sql", ".xml", ".html", ".css"
}
SKIP_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}

@dataclass(frozen=True)
class ResearchDocument:
    source: str
    title: str
    content: str
    metadata: dict[str, Any]

class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0 and data.strip():
            self.parts.append(data)

def _clean_html(raw: str) -> str:
    parser = _HTMLTextParser()
    parser.feed(raw)
    text = html.unescape(" ".join(parser.parts))
    return re.sub(r"\s+", " ", text).strip()

def _request(url: str, *, accept: str = "text/plain", timeout: int = DEFAULT_TIMEOUT, max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "Jenefar-Research/0.1",
            "Accept": accept,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError(f"Response exceeds max_bytes={max_bytes}")
            charset = response.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace"), response.headers.get_content_type()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching {url}: {exc.reason}") from exc

def fetch_url(url: str, *, timeout: int = DEFAULT_TIMEOUT, max_bytes: int = DEFAULT_MAX_BYTES) -> ResearchDocument:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only absolute http(s) URLs are supported")

    raw, content_type = _request(
        url,
        accept="text/html, text/plain, application/json;q=0.9, */*;q=0.1",
        timeout=timeout,
        max_bytes=max_bytes,
    )
    if "html" in content_type or "<html" in raw[:500].lower():
        content = _clean_html(raw)
    elif "json" in content_type:
        try:
            content = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            content = raw
    else:
        content = raw.strip()

    title = parsed.netloc + parsed.path
    return ResearchDocument(
        source=url,
        title=title,
        content=content,
        metadata={"type": "url", "content_type": content_type},
    )

def _github_api(url: str) -> Any:
    raw, _ = _request(url, accept="application/vnd.github+json")
    return json.loads(raw)

def _github_blob(owner: str, repo: str, path: str, ref: str) -> str:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    payload = _github_api(url)
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise ValueError(f"GitHub path is not a file: {path}")
    if payload.get("size", 0) > DEFAULT_MAX_BYTES:
        raise ValueError(f"GitHub file is too large: {path}")
    content = payload.get("content", "")
    if payload.get("encoding") == "base64":
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return str(content)

def fetch_github_repository(
    repository: str,
    *,
    ref: str = "main",
    paths: list[str] | None = None,
    max_files: int = 40,
    max_file_bytes: int = DEFAULT_MAX_BYTES,
) -> list[ResearchDocument]:
    repo = repository.removesuffix(".git").strip("/")
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("Repository must be in owner/repository form")

    owner, name = parts
    selected = [p.strip("/") for p in (paths or []) if p.strip("/")]
    tree = _github_api(f"{GITHUB_API}/repos/{owner}/{name}/git/trees/{ref}?recursive=1")

    if tree.get("truncated"):
        raise RuntimeError("GitHub repository tree is truncated; provide explicit --github-path values.")

    blobs = [
        item for item in tree.get("tree", [])
        if item.get("type") == "blob"
        and PurePosixPath(item.get("path", "")).suffix.lower() in TEXT_EXTENSIONS
        and not any(part in SKIP_PARTS for part in PurePosixPath(item.get("path", "")).parts)
        and int(item.get("size") or 0) <= max_file_bytes
    ]

    if selected:
        allowed = []
        for item in blobs:
            path = item["path"]
            if any(path == target or path.startswith(target.rstrip("/") + "/") for target in selected):
                allowed.append(item)
        blobs = allowed

    blobs.sort(key=lambda item: (
        0 if item["path"].lower() in {"readme.md", "readme.rst", "readme.txt"} else 1,
        item["path"],
    ))

    documents: list[ResearchDocument] = []
    for item in blobs[:max_files]:
        path = item["path"]
        content = _github_blob(owner, name, path, ref)
        documents.append(
            ResearchDocument(
                source=f"https://github.com/{owner}/{name}/blob/{ref}/{path}",
                title=f"{name}: {path}",
                content=content,
                metadata={"type": "github", "repository": f"{owner}/{name}", "ref": ref, "path": path},
            )
        )
    return documents
