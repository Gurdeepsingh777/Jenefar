from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from jenefar.research.sources import GITHUB_API, _github_api

@dataclass(frozen=True)
class RepositoryFile:
    path: str
    size: int
    language: str
    category: str

@dataclass(frozen=True)
class RepositorySummary:
    repository: str
    ref: str
    default_branch: str
    files: list[RepositoryFile]
    languages: dict[str, int]
    has_tests: bool
    has_readme: bool
    entrypoints: list[str]

@dataclass(frozen=True)
class RepositoryPlan:
    repository: str
    task: str
    likely_files: list[str]
    checks: list[str]
    risks: list[str]

LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".c": "C", ".cpp": "C++",
    ".hpp": "C++", ".h": "C/C++", ".rb": "Ruby", ".php": "PHP",
    ".sh": "Shell", ".yaml": "YAML", ".yml": "YAML",
    ".json": "JSON", ".md": "Markdown", ".html": "HTML", ".css": "CSS",
}
ENTRYPOINT_NAMES = {"main.py", "app.py", "server.py", "cli.py", "run.py", "manage.py", "package.json"}

class RepositoryAnalyzer:
    def summarize(self, repository: str, *, ref: str = "main", max_files: int = 500) -> RepositorySummary:
        repo = repository.removesuffix(".git").strip("/")
        parts = repo.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("Repository must be owner/repository")

        owner, name = parts
        meta = _github_api(f"{GITHUB_API}/repos/{owner}/{name}")
        resolved_ref = ref or str(meta.get("default_branch") or "main")
        tree = _github_api(
            f"{GITHUB_API}/repos/{owner}/{name}/git/trees/{resolved_ref}?recursive=1"
        )
        raw_items = [
            item for item in tree.get("tree", [])
            if item.get("type") == "blob"
        ]
        if tree.get("truncated"):
            raise RuntimeError("Repository tree is truncated; use a narrower ref/repository.")

        files: list[RepositoryFile] = []
        languages: dict[str, int] = {}
        for item in raw_items[:max_files]:
            path = str(item.get("path", ""))
            suffix = PurePosixPath(path).suffix.lower()
            language = LANGUAGE_BY_SUFFIX.get(suffix, "Other")
            lower = path.lower()
            if "/test" in lower or lower.startswith("test") or "tests/" in lower:
                category = "test"
            elif suffix in {".md", ".rst"} or PurePosixPath(path).name.lower().startswith("readme"):
                category = "documentation"
            elif PurePosixPath(path).name.lower() in ENTRYPOINT_NAMES:
                category = "entrypoint"
            elif "config" in lower or suffix in {".yaml", ".yml", ".toml", ".ini"}:
                category = "config"
            else:
                category = "source"

            files.append(
                RepositoryFile(
                    path=path,
                    size=int(item.get("size") or 0),
                    language=language,
                    category=category,
                )
            )
            languages[language] = languages.get(language, 0) + 1

        entrypoints = [f.path for f in files if f.category == "entrypoint"]
        has_tests = any(f.category == "test" for f in files)
        has_readme = any(f.category == "documentation" and "readme" in f.path.lower() for f in files)
        return RepositorySummary(
            repository=f"{owner}/{name}",
            ref=resolved_ref,
            default_branch=str(meta.get("default_branch") or "main"),
            files=files,
            languages=languages,
            has_tests=has_tests,
            has_readme=has_readme,
            entrypoints=entrypoints,
        )

    def plan_change(self, repository: str, task: str, *, ref: str = "main") -> RepositoryPlan:
        summary = self.summarize(repository, ref=ref)
        normalized = task.lower()
        candidates: list[str] = []

        for file in summary.files:
            path = file.path.lower()
            if any(word in normalized for word in ("test", "bug", "error", "fix")) and file.category == "test":
                candidates.append(file.path)
            if any(word in normalized for word in ("python", "script", "api")) and file.language == "Python":
                candidates.append(file.path)
            if any(word in normalized for word in ("frontend", "ui", "web")) and file.language in {"JavaScript", "TypeScript", "HTML", "CSS"}:
                candidates.append(file.path)
            if "config" in normalized and file.category == "config":
                candidates.append(file.path)

        if not candidates:
            candidates = summary.entrypoints[:5] or [f.path for f in summary.files if f.category == "source"][:5]

        unique = list(dict.fromkeys(candidates))[:12]
        checks = ["run the repository's existing test suite"]
        if any("python" == lang for lang in summary.languages):
            checks.append("run Python compile/type/lint checks used by the repository")
        if summary.has_tests:
            checks.append("update/add focused regression tests")
        risks = []
        if not summary.has_tests:
            risks.append("repository does not expose an obvious test directory")
        if any(f.size > 1_000_000 for f in summary.files):
            risks.append("repository contains large files; avoid loading them blindly")
        risks.append("never execute downloaded repository code automatically")

        return RepositoryPlan(
            repository=summary.repository,
            task=task,
            likely_files=unique,
            checks=checks,
            risks=risks,
        )
