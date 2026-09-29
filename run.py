from __future__ import annotations

import argparse
import importlib.util

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jenefar modular multi-agent AI assistant"
    )
    parser.add_argument("--voice", action="store_true", help="run bounded microphone -> STT -> agent -> TTS mode")
    parser.add_argument("--voice-continuous", action="store_true", help="run continuous microphone VAD -> STT -> agent -> TTS mode")
    parser.add_argument("--avatar", action="store_true", help="show Jenefar's local real-time particle avatar UI")
    parser.add_argument("--avatar-port", type=int, default=8787, help="local avatar UI port")
    parser.add_argument("--discover-tools", action="store_true", help="list detected Kali/Linux tools without executing them")
    parser.add_argument("--doctor", action="store_true", help="check local Jenefar dependencies/configuration")
    parser.add_argument("--index-file", metavar="PATH", help="index one supported text/code file into long-term memory")
    parser.add_argument("--index-dir", metavar="PATH", help="index supported text/code files under a directory")
    parser.add_argument("--index-document", metavar="PATH", help="extract PDF/DOCX/text content and index it")
    parser.add_argument("--index-url", metavar="URL", help="fetch one HTTP(S) page/API response and index it")
    parser.add_argument("--index-github", metavar="OWNER/REPO", help="fetch a public GitHub repository and index supported text/code files")
    parser.add_argument("--analyze-github", metavar="OWNER/REPO", help="summarize a public GitHub repository without executing code")
    parser.add_argument("--plan-github", metavar="OWNER/REPO", help="create a read-only repository change plan")
    parser.add_argument("--plan-task", help="task description used with --plan-github")
    parser.add_argument("--github-ref", default="main", help="GitHub branch/tag/commit")
    parser.add_argument("--github-path", action="append", default=[], help="Restrict --index-github to this file/directory path; repeatable")
    parser.add_argument("--github-max-files", type=int, default=40, help="Maximum GitHub files to index")
    parser.add_argument("--memory-search", metavar="QUERY", help="search persistent Jenefar memory/RAG index")
    return parser

def doctor() -> int:
    print("[JENEFAR] Doctor")
    checks = {
        "yaml": "yaml",
        "dotenv": "dotenv",
        "openai": "openai",
        "sounddevice": "sounddevice",
        "pypdf": "pypdf",
        "docx": "docx",
    }
    failed = False
    for label, module in checks.items():
        ok = importlib.util.find_spec(module) is not None
        print(f"  {label:12} {'OK' if ok else 'MISSING'}")
        failed = failed or not ok

    try:
        from jenefar.core.config import load_config
        config = load_config()
        print(f"  config       OK ({config.name})")
        print(f"  api key      {'SET' if __import__('os').getenv('OPENAI_API_KEY') else 'NOT SET'}")
    except Exception as exc:
        print(f"  config       ERROR ({type(exc).__name__}: {exc})")
        failed = True

    if failed:
        print("[JENEFAR] Doctor found missing/invalid local dependencies.")
        return 1
    print("[JENEFAR] Doctor checks passed.")
    return 0

def github_command(args: argparse.Namespace) -> int:
    from jenefar.coding.repository import RepositoryAnalyzer

    analyzer = RepositoryAnalyzer()

    if args.analyze_github:
        summary = analyzer.summarize(args.analyze_github, ref=args.github_ref)
        print(f"Repository: {summary.repository}@{summary.ref}")
        print(f"Default branch: {summary.default_branch}")
        print(f"Files: {len(summary.files)}")
        print(f"Languages: {summary.languages}")
        print(f"Tests: {'yes' if summary.has_tests else 'no'}")
        print(f"README: {'yes' if summary.has_readme else 'no'}")
        print(f"Entrypoints: {summary.entrypoints}")
        for item in summary.files[:50]:
            print(f"{item.category:12} {item.language:12} {item.size:8} {item.path}")
        return 0

    if not args.plan_task:
        print("[JENEFAR] --plan-github requires --plan-task")
        return 2

    plan = analyzer.plan_change(args.plan_github, args.plan_task, ref=args.github_ref)
    print(f"Repository: {plan.repository}")
    print(f"Task: {plan.task}")
    print("Likely files:")
    for path in plan.likely_files:
        print(f"  - {path}")
    print("Checks:")
    for check in plan.checks:
        print(f"  - {check}")
    print("Risks:")
    for risk in plan.risks:
        print(f"  - {risk}")
    return 0

def memory_command(args: argparse.Namespace) -> int:
    from jenefar.memory.ingest import ingest_directory, ingest_file
    from jenefar.memory.store import MemoryStore
    from jenefar.research.ingest import index_github, index_url

    store = MemoryStore()

    if args.index_file:
        added = ingest_file(args.index_file, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_file}")
        return 0

    if args.index_dir:
        added = ingest_directory(args.index_dir, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_dir}")
        return 0

    if args.index_document:
        from jenefar.docs.ingest import ingest_document
        added = ingest_document(args.index_document, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_document}")
        return 0

    if args.index_url:
        added = index_url(args.index_url, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_url}")
        return 0

    if args.index_github:
        if args.github_max_files < 1:
            print("[JENEFAR] --github-max-files must be >= 1")
            return 2
        added = index_github(
            args.index_github,
            store,
            ref=args.github_ref,
            paths=args.github_path,
            max_files=args.github_max_files,
        )
        print(f"[JENEFAR] Indexed {added} chunk(s) from GitHub {args.index_github}@{args.github_ref}")
        return 0

    if args.memory_search:
        hits = store.search(args.memory_search, limit=8)
        if not hits:
            print("[JENEFAR] No matching memory found.")
            return 0
        for index, hit in enumerate(hits, start=1):
            print(f"\n[{index}] {hit.title}")
            print(f"source: {hit.source}")
            print(hit.content)
        return 0

    return 1

def main() -> int:
    args = build_parser().parse_args()

    if args.doctor:
        return doctor()

    if args.analyze_github and args.plan_github:
        print("[JENEFAR] Use only one GitHub analysis option at a time.")
        return 2

    if args.analyze_github or args.plan_github:
        try:
            return github_command(args)
        except Exception as exc:
            print(f"[JENEFAR] GitHub analysis error: {type(exc).__name__}: {exc}")
            return 1

    memory_values = [
        args.index_file,
        args.index_dir,
        args.index_document,
        args.index_url,
        args.index_github,
        args.memory_search,
    ]
    if any(value is not None for value in memory_values):
        if sum(value is not None for value in memory_values) != 1:
            print("[JENEFAR] Use only one memory/index option at a time.")
            return 2
        try:
            return memory_command(args)
        except Exception as exc:
            print(f"[JENEFAR] Research/memory error: {type(exc).__name__}: {exc}")
            return 1

    if args.discover_tools:
        from jenefar.tools.discovery import discover_tools
        for tool in discover_tools():
            status = "installed" if tool.installed else "missing"
            print(f"{tool.name:16} {status:9} [{tool.category}]")
        return 0

    from jenefar.core.orchestrator import JenefarOrchestrator

    avatar = None
    avatar_server = None
    if args.avatar:
        import webbrowser
        from jenefar.avatar.controller import AvatarController
        from jenefar.avatar.server import AvatarServer

        avatar = AvatarController()
        avatar_server = AvatarServer(avatar, port=args.avatar_port)
        avatar_server.start()
        print(f"[JENEFAR] Avatar UI: {avatar_server.url}")
        try:
            webbrowser.open(avatar_server.url)
        except Exception:
            pass

    if args.voice_continuous:
        from jenefar.voice.continuous import ContinuousVoiceRuntime
        ContinuousVoiceRuntime(
            JenefarOrchestrator(avatar=avatar),
            avatar=avatar,
        ).run()
        if avatar_server is not None:
            avatar_server.stop()
        return 0

    try:
        if args.voice:
            from jenefar.voice.openai_voice import OpenAIVoiceRuntime
            OpenAIVoiceRuntime(
                JenefarOrchestrator(avatar=avatar),
                avatar=avatar,
            ).run()
            return 0

        JenefarOrchestrator(avatar=avatar).run()
        return 0
    finally:
        if avatar_server is not None:
            avatar_server.stop()

if __name__ == "__main__":
    raise SystemExit(main())
