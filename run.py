from __future__ import annotations

import argparse
import importlib.util

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jenefar modular multi-agent AI assistant"
    )
    parser.add_argument("--voice", action="store_true", help="run microphone -> STT -> agent -> TTS mode")
    parser.add_argument("--discover-tools", action="store_true", help="list detected Kali/Linux tools without executing them")
    parser.add_argument("--doctor", action="store_true", help="check local Jenefar dependencies/configuration")
    parser.add_argument("--index-file", metavar="PATH", help="index one supported text/code file into long-term memory")
    parser.add_argument("--index-dir", metavar="PATH", help="index supported text/code files under a directory")
    parser.add_argument("--memory-search", metavar="QUERY", help="search persistent Jenefar memory/RAG index")
    return parser

def doctor() -> int:
    print("[JENEFAR] Doctor")
    checks = {
        "yaml": "yaml",
        "dotenv": "dotenv",
        "openai": "openai",
        "sounddevice": "sounddevice",
    }
    failed = False

    for label, module in checks.items():
        ok = importlib.util.find_spec(module) is not None
        status = "OK" if ok else "MISSING"
        print(f"  {label:12} {status}")
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

def memory_command(index_file: str | None, index_dir: str | None, query: str | None) -> int:
    from jenefar.memory.ingest import ingest_directory, ingest_file
    from jenefar.memory.store import MemoryStore

    store = MemoryStore()

    if index_file:
        added = ingest_file(index_file, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {index_file}")
        return 0

    if index_dir:
        added = ingest_directory(index_dir, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {index_dir}")
        return 0

    if query:
        hits = store.search(query, limit=8)
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

    memory_args = [args.index_file, args.index_dir, args.memory_search]
    if any(value is not None for value in memory_args):
        if sum(value is not None for value in memory_args) != 1:
            print("[JENEFAR] Use only one memory/index option at a time.")
            return 2
        try:
            return memory_command(args.index_file, args.index_dir, args.memory_search)
        except Exception as exc:
            print(f"[JENEFAR] Memory error: {type(exc).__name__}: {exc}")
            return 1

    if args.discover_tools:
        from jenefar.tools.discovery import discover_tools
        for tool in discover_tools():
            status = "installed" if tool.installed else "missing"
            print(f"{tool.name:16} {status:9} [{tool.category}]")
        return 0

    from jenefar.core.orchestrator import JenefarOrchestrator

    if args.voice:
        from jenefar.voice.openai_voice import OpenAIVoiceRuntime
        OpenAIVoiceRuntime(JenefarOrchestrator()).run()
        return 0

    JenefarOrchestrator().run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
