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
        print(f"  api key      {'SET' if importlib.util.find_spec('dotenv') and __import__('os').getenv('OPENAI_API_KEY') else 'NOT SET'}")
    except Exception as exc:
        print(f"  config       ERROR ({type(exc).__name__}: {exc})")
        failed = True

    if failed:
        print("[JENEFAR] Doctor found missing/invalid local dependencies.")
        return 1

    print("[JENEFAR] Doctor checks passed.")
    return 0

def main() -> int:
    args = build_parser().parse_args()

    if args.doctor:
        return doctor()

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
