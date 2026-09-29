from __future__ import annotations

import asyncio
import os
import time


class OpenAIVoiceRuntime:
    """Optional bounded microphone/STT/TTS loop."""

    def __init__(self, orchestrator, seconds: int = 8, avatar=None):
        self.orchestrator = orchestrator
        self.seconds = seconds
        self.avatar = avatar

    async def _listen(self) -> str:
        from openai import AsyncOpenAI
        from openai.helpers import Microphone

        client = AsyncOpenAI()
        recording = await Microphone(timeout=self.seconds).record()
        result = await client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe"),
            file=recording,
        )
        return result.text.strip()

    async def _speak(self, text: str) -> None:
        from openai import AsyncOpenAI
        from openai.helpers import LocalAudioPlayer

        client = AsyncOpenAI()
        animation = None
        if self.avatar is not None:
            animation = asyncio.create_task(self._animate_speaking(text))

        try:
            async with client.audio.speech.with_streaming_response.create(
                model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
                voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
                response_format="pcm",
                input=text,
            ) as response:
                await LocalAudioPlayer().play(response)
        finally:
            if animation is not None:
                animation.cancel()
                try:
                    await animation
                except asyncio.CancelledError:
                    pass

    async def _animate_speaking(self, text: str) -> None:
        words = max(1, len(text.split()))
        duration = max(0.8, words * 0.24)
        started = time.monotonic()

        while True:
            elapsed = time.monotonic() - started
            phase = (elapsed / duration) * 18.0
            level = 0.12 + 0.68 * ((0.5 + 0.5 * __import__("math").sin(phase)) ** 1.8)
            self.avatar.publish("speaking", text, level=level)
            await asyncio.sleep(0.09)

    def run(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            print("[JENEFAR] Set OPENAI_API_KEY before using --voice.")
            return

        print(
            "[JENEFAR] Voice mode. Speak for up to",
            self.seconds,
            "seconds per turn.",
        )
        print("[JENEFAR] Say 'Hi Jenefar' or 'Hello Jenefar' in the recording.")

        while True:
            try:
                if self.avatar is not None:
                    self.avatar.publish("listening", "Listening…")
                text = asyncio.run(self._listen())
            except KeyboardInterrupt:
                print("\n[JENEFAR] Voice mode stopped.")
                return
            except Exception as exc:
                print(f"[JENEFAR] Voice error: {type(exc).__name__}: {exc}")
                return

            if text.lower().strip() == "exit":
                print("[JENEFAR] Goodbye.")
                return
            if not text:
                continue

            if self.orchestrator.state.name == "SLEEPING":
                if not self.orchestrator.wakeword.detect(text):
                    if self.avatar is not None:
                        self.avatar.publish("idle", "")
                    continue
                command = self.orchestrator.wakeword.remove_wake_phrase(text)
                if not command:
                    answer = "Yes, I'm listening."
                else:
                    answer = self.orchestrator.handle(command)
            else:
                answer = self.orchestrator.handle(text)

            print(f"[USER/STT] {text}")
            print(f"[JENEFAR] {answer}")

            if self.avatar is not None:
                self.avatar.publish("speaking", answer, level=0.2)

            try:
                asyncio.run(self._speak(answer))
            except Exception as exc:
                print(f"[JENEFAR] TTS unavailable: {type(exc).__name__}: {exc}")
            finally:
                if self.avatar is not None:
                    self.avatar.publish("idle", "")
