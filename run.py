from __future__ import annotations

import argparse

from jenefar.core.orchestrator import JenefarOrchestrator

def main() -> None:
    parser = argparse.ArgumentParser(description="Run Jenefar.")
    parser.add_argument("--voice", action="store_true", help="run optional microphone/STT/TTS mode")
    args = parser.parse_args()

    if not args.voice:
        JenefarOrchestrator().run()
        return

    from jenefar.voice.openai_voice import OpenAIVoiceRuntime
    OpenAIVoiceRuntime(JenefarOrchestrator()).run()

if __name__ == "__main__":
    main()
