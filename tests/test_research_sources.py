from pathlib import Path

from jenefar.research.sources import ResearchDocument, _clean_html
from jenefar.research.ingest import ingest_research_document
from jenefar.memory.store import MemoryStore

def test_clean_html_removes_script_and_navigation():
    text = _clean_html("<html><nav>menu</nav><h1>Hello</h1><script>x()</script><p>world</p></html>")
    assert text == "Hello world"

def test_research_document_ingest(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.db")
    doc = ResearchDocument(
        source="https://example.com",
        title="Example",
        content="Jenefar research connector",
        metadata={"type": "url"},
    )
    assert ingest_research_document(doc, store) == 1
    assert store.search("research connector")[0].source == "https://example.com"


def test_source_validation():
    from pytest import raises
    from jenefar.research.sources import fetch_url, fetch_github_repository
    with raises(ValueError):
        fetch_url("ftp://example.com/file")
    with raises(ValueError):
        fetch_github_repository("invalid-repo")

def test_read_only_tools_are_registered():
    from jenefar.tools.broker import ToolBroker
    names = {tool["name"] for tool in ToolBroker().schemas()}
    assert "research_fetch_url" in names
    assert "research_fetch_github" in names
