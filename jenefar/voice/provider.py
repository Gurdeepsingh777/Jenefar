from __future__ import annotations

import asyncio
import io
import math
import os
import tempfile
import time
import wave
from pathlib import Path

from jenefar.core.provider_pool import ProviderPool, is_retryable_provider_error


class ProviderVoiceRuntime:
    """Provider-aware microphone -> STT -> agent -> TTS runtime with audio failover."""

    def __init__(self, orchestrator, seconds: int = 8, avatar=None):
        self.orchestrator = orchestrator
        self.seconds = seconds
        self.avatar = avatar
        self._audio_pool = ProviderPool()

    @staticmethod
    def _direct_openai_key() -> str:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return "" if not key or key.startswith("sk-or-") else key

    @classmethod
    def _configured_audio_providers(cls) -> list[str]:
        raw = os.getenv("JENEFAR_VOICE_PROVIDER_ORDER", "openai,groq")
        requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
        valid = [name for name in ("openai", "groq") if name in requested]
        ordered = valid or ["openai", "groq"]
        return [name for name in ordered if cls._provider_configured(name)]

    @classmethod
    def _provider_configured(cls, name: str) -> bool:
        if name == "openai":
            return bool(cls._direct_openai_key())
        if name == "groq":
            return bool(os.getenv("GROQ_API_KEY", "").strip())
        return False

    @classmethod
    def audio_status(cls) -> dict[str, dict | None]:
        providers = cls._configured_audio_providers()
        primary = providers[0] if providers else None
        fallback = providers[1:] if len(providers) > 1 else []
        result: dict[str, dict | None] = {"stt": None, "tts": None}
        if primary:
            result["stt"] = {
                "provider": primary,
                "model": cls._stt_model(primary),
                "fallback": fallback,
            }
            result["tts"] = {
                "provider": primary,
                "model": cls._tts_model(primary),
                "fallback": fallback,
            }
        return result

    @staticmethod
    def _stt_model(provider: str) -> str:
        return (
            os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
            if provider == "openai"
            else os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
        )

    @staticmethod
    def _tts_model(provider: str) -> str:
        return (
            os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
            if provider == "openai"
            else os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
        )

    def _provider_order(self) -> list[str]:
        raw = os.getenv("JENEFAR_VOICE_PROVIDER_ORDER", "openai,groq")
        requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
        order = [name for name in requested if name in ("openai", "groq")]
        if not order:
            order = ["openai", "groq"]
        return [name for name in order if self._provider_configured(name)]

    def _cooldown_seconds(self, exc: Exception) -> float:
        message = str(exc).lower()
        if "insufficient_quota" in message or "credit_balance_exhausted" in message:
            return float(os.getenv("JENEFAR_VOICE_QUOTA_COOLDOWN_SECONDS", "3600"))
        return float(os.getenv("JENEFAR_PROVIDER_COOLDOWN_SECONDS", "60"))

    def _mark_failed_provider(self, provider: str, exc: Exception) -> None:
        self._audio_pool.cooldown(provider, self._cooldown_seconds(exc))

    @staticmethod
    def _wav_bytes(pcm: bytes, sample_rate: int = 16_000, channels: int = 1) -> io.BytesIO:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        output.seek(0)
        output.name = "jenefar_utterance.wav"
        return output

    @staticmethod
    def _record_microphone(seconds: int) -> bytes:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Voice input requires sounddevice and numpy. Install requirements.txt."
            ) from exc
        sample_rate = int(os.getenv("JENEFAR_VOICE_CAPTURE_RATE", "16000"))
        channels = int(os.getenv("JENEFAR_VOICE_CAPTURE_CHANNELS", "1"))
        frames = max(1, int(seconds * sample_rate))
        audio = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="int16")
        sd.wait()
        return np.asarray(audio, dtype=np.int16).tobytes()

    @staticmethod
    async def _transcribe_openai(audio: io.BytesIO) -> str:
        from openai import AsyncOpenAI

        audio.seek(0)
        client = AsyncOpenAI(api_key=ProviderVoiceRuntime._direct_openai_key())
        result = await client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe"),
            file=audio,
        )
        return str(result.text or "").strip()

    @staticmethod
    async def _transcribe_groq(audio: io.BytesIO) -> str:
        from openai import OpenAI

        audio.seek(0)
        client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY", "").strip(),
            base_url="https://api.groq.com/openai/v1",
        )

        def request() -> str:
            audio.seek(0)
            result = client.audio.transcriptions.create(
                model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3"),
                file=audio,
                language=os.getenv("GROQ_STT_LANGUAGE", "hi") or None,
                response_format="json",
                temperature=0.0,
            )
            return str(result.text or "").strip()

        return await asyncio.to_thread(request)

    async def transcribe_pcm(
        self, pcm: bytes, *, sample_rate: int = 16_000, channels: int = 1
    ) -> str:
        audio = self._wav_bytes(pcm, sample_rate=sample_rate, channels=channels)
        providers = self._provider_order()
        if not providers:
            raise RuntimeError(
                "No speech-to-text provider is configured. Set OPENAI_API_KEY or GROQ_API_KEY."
            )

        last_error: Exception | None = None
        for provider in providers:
            if not self._audio_pool.available(provider):
                continue
            try:
                if provider == "openai":
                    return await self._transcribe_openai(audio)
                return await self._transcribe_groq(audio)
            except Exception as exc:
                last_error = exc
                if not is_retryable_provider_error(exc):
                    raise
                self._mark_failed_provider(provider, exc)
                print(
                    f"[JENEFAR] STT provider {provider} failed; "
                    f"trying the next configured provider: {type(exc).__name__}: {exc}"
                )

        if last_error is not None:
            raise RuntimeError(
                "All configured STT providers failed. "
                "Check provider quota/API keys or wait for the provider cooldown."
            ) from last_error
        raise RuntimeError("No currently available STT provider.")

    async def _listen(self) -> str:
        pcm = await asyncio.to_thread(self._record_microphone, self.seconds)
        return await self.transcribe_pcm(pcm)

    @staticmethod
    def _tts_chunks(text: str, max_chars: int = 190) -> list[str]:
        clean = " ".join(str(text).split()).strip()
        if not clean:
            return []
        chunks: list[str] = []
        while len(clean) > max_chars:
            cut = clean.rfind(" ", 0, max_chars + 1)
            if cut < max_chars // 2:
                cut = clean.rfind(".", 0, max_chars + 1)
            if cut <= 0:
                cut = max_chars
            chunks.append(clean[:cut].strip())
            clean = clean[cut:].strip()
        if clean:
            chunks.append(clean)
        return chunks

    @staticmethod
    def _play_wav(path: str | Path) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Voice playback requires sounddevice and numpy. Install requirements.txt."
            ) from exc
        with wave.open(str(path), "rb") as wav:
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)
        sd.play(audio, samplerate=sample_rate)
        sd.wait()

    async def _speak_openai(self, text: str) -> None:
        from openai import AsyncOpenAI
        from openai.helpers import LocalAudioPlayer

        client = AsyncOpenAI(api_key=self._direct_openai_key())
        animation = asyncio.create_task(self._animate_speaking(text)) if self.avatar else None
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

    async def _speak_groq(self, text: str) -> None:
        from openai import OpenAI

        client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY", "").strip(),
            base_url="https://api.groq.com/openai/v1",
        )
        voice = os.getenv("GROQ_TTS_VOICE", "troy").strip() or "troy"
        model = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english").strip()
        animation = asyncio.create_task(self._animate_speaking(text)) if self.avatar else None
        try:
            for chunk in self._tts_chunks(text):
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", prefix="jenefar_tts_", delete=False
                ) as tmp:
                    output_path = tmp.name
                try:
                    def request() -> None:
                        response = client.audio.speech.create(
                            model=model, voice=voice, input=chunk, response_format="wav"
                        )
                        response.write_to_file(output_path)

                    await asyncio.to_thread(request)
                    await asyncio.to_thread(self._play_wav, output_path)
                finally:
                    try:
                        os.unlink(output_path)
                    except FileNotFoundError:
                        pass
        finally:
            if animation is not None:
                animation.cancel()
                try:
                    await animation
                except asyncio.CancelledError:
                    pass

    async def speak(self, text: str) -> None:
        providers = self._provider_order()
        if not providers:
            raise RuntimeError(
                "No text-to-speech provider is configured. Set OPENAI_API_KEY or GROQ_API_KEY."
            )

        last_error: Exception | None = None
        for provider in providers:
            if not self._audio_pool.available(provider):
                continue
            try:
                if provider == "openai":
                    await self._speak_openai(text)
                else:
                    await self._speak_groq(text)
                return
            except Exception as exc:
                last_error = exc
                if not is_retryable_provider_error(exc):
                    raise
                self._mark_failed_provider(provider, exc)
                print(
                    f"[JENEFAR] TTS provider {provider} failed; "
                    f"trying the next configured provider: {type(exc).__name__}: {exc}"
                )

        if last_error is not None:
            raise RuntimeError(
                "All configured TTS providers failed. "
                "Check provider quota/API keys or wait for the provider cooldown."
            ) from last_error
        raise RuntimeError("No currently available TTS provider.")

    async def _speak(self, text: str) -> None:
        await self.speak(text)

    async def _animate_speaking(self, text: str) -> None:
        if self.avatar is None:
            return
        duration = max(0.8, len(text.split()) * 0.24)
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            phase = (elapsed / duration) * 18.0
            level = 0.12 + 0.68 * ((0.5 + 0.5 * math.sin(phase)) ** 1.8)
            self.avatar.publish("speaking", text, level=level)
            await asyncio.sleep(0.09)

    def provider_status_line(self) -> str:
        status = self.audio_status()
        stt = status["stt"] or {"provider": "none", "model": "none", "fallback": []}
        tts = status["tts"] or {"provider": "none", "model": "none", "fallback": []}
        stt_fallback = ",".join(stt.get("fallback", [])) or "none"
        tts_fallback = ",".join(tts.get("fallback", [])) or "none"
        return (
            f"STT={stt['provider']}/{stt['model']} fallback={stt_fallback} | "
            f"TTS={tts['provider']}/{tts['model']} fallback={tts_fallback}"
        )

    def run(self) -> None:
        status = self.audio_status()
        print("[JENEFAR] Voice mode.")
        if status["stt"]:
            print(
                f"[JENEFAR] STT: {status['stt']['provider']} / {status['stt']['model']} "
                f"(fallback={','.join(status['stt'].get('fallback', [])) or 'none'})"
            )
        else:
            print("[JENEFAR] STT: NOT CONFIGURED")
        if status["tts"]:
            print(
                f"[JENEFAR] TTS: {status['tts']['provider']} / {status['tts']['model']} "
                f"(fallback={','.join(status['tts'].get('fallback', [])) or 'none'})"
            )
        else:
            print("[JENEFAR] TTS: NOT CONFIGURED")
        print("[JENEFAR] Speak 'Hi Jenefar' or 'Hello Jenefar'. Say 'exit' to stop.")
        if not status["stt"]:
            print("[JENEFAR] Set OPENAI_API_KEY or GROQ_API_KEY before using voice mode.")
            return
        if not status["tts"]:
            print("[JENEFAR] Speech input is available, but no TTS provider is configured.")

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
                        command, response_language=response_language
                    )
            else:
                answer = self.orchestrator.handle(text)
            print(f"[USER/STT] {text}")
            print(f"[JENEFAR] {answer}")
            try:
                asyncio.run(self.speak(answer))
            except Exception as exc:
                print(f"[JENEFAR] TTS error: {type(exc).__name__}: {exc}")
