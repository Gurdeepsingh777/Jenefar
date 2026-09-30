from __future__ import annotations

import asyncio
import os
import time


class ProviderVoiceRuntime:
    """Voice loop using provider-independent Jenefar responses plus OpenAI-compatible TTS."""

    def __init__(self, orchestrator, seconds: int = 8, avatar=None):
        self.orchestrator = orchestrator
        self.seconds = seconds
        self.avatar = avatar

    async def _listen(self) -> str:
        from openai import AsyncOpenAI
        from openai.helpers import Microphone

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key.startswith("sk-or-"):
            raise RuntimeError(
                "Voice STT currently requires a direct OPENAI_API_KEY; "
                "OpenRouter/Gemini/Groq keys are not valid for OpenAI audio APIs."
            )

        client = AsyncOpenAI(api_key=api_key)
        recording = await Microphone(timeout=self.seconds).record()
        result = await client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe"),
            file=recording,
        )
        return result.text.strip()

    async def _speak(self, text: str) -> None:
        from openai import AsyncOpenAI
        from openai.helpers import LocalAudioPlayer

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key.startswith("sk-or-"):
            raise RuntimeError(
                "Voice TTS currently requires a direct OPENAI_API_KEY; "
                "OpenRouter/Gemini/Groq text keys do not provide OpenAI audio endpoints."
            )

        client = AsyncOpenAI(api_key=api_key)
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
        if self.avatar is None:
            return
        duration = max(0.8, len(text.split()) * 0.24)
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            phase = (elapsed / duration) * 18.0
            level = 0.12 + 0.68 * ((0.5 + 0.5 * __import__("math").sin(phase)) ** 1.8)
            self.avatar.publish("speaking", text, level=level)
            await asyncio.sleep(0.09)

    def run(self) -> None:
        print("[JENEFAR] Voice mode.")
        print("[JENEFAR] Speak 'Hi Jenefar' or 'Hello Jenefar'.")
        if os.getenv("OPENAI_API_KEY", "").strip().startswith("sk-or-"):
            print("[JENEFAR] Note: text LLM can use OpenRouter, but microphone/TTS requires direct OpenAI API credentials.")

        while True:
            try:
                text = asyncio.run(self._listen())
            except KeyboardInterrupt:
                print("\n[JENEFAR] Voice mode stopped.")
                return
            except Exception as exc:
                print(f"[JENEFAR] Voice error: {type(exc).__name__}: {exc}")
                return

            if not text:
                continue
            if text.lower().strip() == "exit":
                print("[JENEFAR] Goodbye.")
                return

            if self.orchestrator.state.name == "SLEEPING":
                matched = self.orchestrator.wakeword.matched_phrase(text)
                if matched is None:
                    continue
                command = self.orchestrator.wakeword.remove_wake_phrase(text)
                response_language = "Hinglish" if matched == "hello jenefar" else None
                if not command:
                    answer = (
                        "Haan, boliye. Main sun rahi hoon."
                        if response_language == "Hinglish"
                        else "Yes, I'm listening."
                    )
                else:
                    answer = self.orchestrator.handle(
                        command,
                        response_language=response_language,
                    )
            else:
                answer = self.orchestrator.handle(text)

            print(f"[USER/STT] {text}")
            print(f"[JENEFAR] {answer}")

            try:
                await_result = self._speak(answer)
                asyncio.run(await_result)
            except Exception as exc:
                print(f"[JENEFAR] TTS error: {type(exc).__name__}: {exc}")
