from __future__ import annotations

import argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jenefar modular multi-agent AI assistant"
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="run microphone -> STT -> agent -> TTS mode",
    )
    parser.add_argument(
        "--discover-tools",
        action="store_true",
        help="list detected Kali/Linux tools without executing them",
    )
    return parser

def main() -> None:
    args = build_parser().parse_args()

    # Keep the CLI lightweight: optional subsystems are imported only when used.
    if args.discover_tools:
        from jenefar.tools.discovery import discover_tools

        for tool in discover_tools():
            status = "installed" if tool.installed else "missing"
            print(f"{tool.name:16} {status:9} [{tool.category}]")
        return

    from jenefar.core.orchestrator import JenefarOrchestrator

    if args.voice:
        from jenefar.voice.openai_voice import OpenAIVoiceRuntime

        OpenAIVoiceRuntime(JenefarOrchestrator()).run()
        return

    JenefarOrchestrator().run()

if __name__ == "__main__":
    main()
