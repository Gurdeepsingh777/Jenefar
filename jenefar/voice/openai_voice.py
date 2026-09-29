from __future__ import annotations

import asyncio
import os

class OpenAIVoiceRuntime:
    """Optional push-to-talk style loop using OpenAI voice helpers.

    Each turn records a bounded window, transcribes it, then feeds the same
    text command path used by the normal orchestrator.
    """

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
        async with client.audio.speech.with_streaming_response.create(
            model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
            response_format="pcm",
            input=text,
        ) as response:
            await LocalAudioPlayer().play(response)

    def run(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            print("[JENEFAR] Set OPENAI_API_KEY before using --voice.")
            return
        print("[JENEFAR] Voice mode. Speak for up to", self.seconds, "seconds per turn.")
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

            if text.lower() == "exit":
                print("[JENEFAR] Goodbye.")
                return
            if not text:
                continue

            if self.orchestrator.state.name == "SLEEPING":
                if not self.orchestrator.wakeword.detect(text):
                    continue
                command = self.orchestrator.wakeword.remove_wake_phrase(text)
                if not command:
                    asyncio.run(self._speak("Yes, I'm listening."))
                    continue
                answer = self.orchestrator.handle(command)
            else:
                answer = self.orchestrator.handle(text)

            print(f"[USER/STT] {text}")
            print(f"[JENEFAR] {answer}")
            if self.avatar is not None:
                self.avatar.publish("speaking", answer)
            try:
                asyncio.run(self._speak(answer))
            except Exception as exc:
                print(f"[JENEFAR] TTS unavailable: {type(exc).__name__}: {exc}")
            finally:
                if self.avatar is not None:
                    self.avatar.publish("idle", "")
