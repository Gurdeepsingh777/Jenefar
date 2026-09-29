from __future__ import annotations

import argparse

from jenefar.core.orchestrator import JenefarOrchestrator

def main() -> None:
    parser = argparse.ArgumentParser(description="Run Jenefar.")
    parser.add_argument("--voice", action="store_true", help="run optional microphone/STT/TTS mode")
    parser.add_argument("--discover-tools", action="store_true", help="list detected Kali/Linux tools without executing them")
    args = parser.parse_args()

    if args.discover_tools:
        from jenefar.tools.discovery import discover_tools
        for tool in discover_tools():
            status = "installed" if tool.installed else "missing"
            print(f"{tool.name:16} {status:9} [{tool.category}]")
        return

    if args.voice:
        from jenefar.voice.openai_voice import OpenAIVoiceRuntime
        OpenAIVoiceRuntime(JenefarOrchestrator()).run()
        return

    JenefarOrchestrator().run()

if __name__ == "__main__":
    main()
