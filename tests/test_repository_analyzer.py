import jenefar.coding.repository as repository_module
from jenefar.coding.repository import RepositoryAnalyzer

def test_repository_summary_uses_github_metadata(monkeypatch):
    def fake_api(url):
        if url.endswith("/repos/acme/demo"):
            return {"default_branch": "main"}
        return {
            "tree": [
                {"type": "blob", "path": "README.md", "size": 10},
                {"type": "blob", "path": "main.py", "size": 20},
                {"type": "blob", "path": "tests/test_main.py", "size": 30},
                {"type": "blob", "path": "config.yaml", "size": 40},
            ]
        }
    monkeypatch.setattr(repository_module, "_github_api", fake_api)
    summary = RepositoryAnalyzer().summarize("acme/demo")
    assert summary.repository == "acme/demo"
    assert summary.has_readme is True
    assert summary.has_tests is True
    assert summary.entrypoints == ["main.py"]
    assert summary.languages["Python"] == 2
