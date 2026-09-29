from __future__ import annotations

import asyncio
import io
import os
import queue
import threading
import time
import wave
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VoiceConfig:
    sample_rate: int = 24_000
    channels: int = 1
    block_ms: int = 100
    start_threshold: float = 0.015
    stop_threshold: float = 0.010
    silence_ms: int = 850
    max_utterance_seconds: float = 12.0


class ContinuousVoiceRuntime:
    """Continuous microphone -> VAD -> STT -> Jenefar -> TTS runtime.

    This keeps wake-word and orchestration in Jenefar while continuously
    monitoring the microphone. Audio is only sent for detected utterances.
    """

    def __init__(self, orchestrator, config: VoiceConfig | None = None, avatar=None):
        self.orchestrator = orchestrator
        self.avatar = avatar
        self.config = config or VoiceConfig(
            sample_rate=int(os.getenv("JENEFAR_VOICE_SAMPLE_RATE", "24000")),
            block_ms=int(os.getenv("JENEFAR_VOICE_BLOCK_MS", "100")),
            start_threshold=float(os.getenv("JENEFAR_VOICE_START_THRESHOLD", "0.015")),
            stop_threshold=float(os.getenv("JENEFAR_VOICE_STOP_THRESHOLD", "0.010")),
            silence_ms=int(os.getenv("JENEFAR_VOICE_SILENCE_MS", "850")),
            max_utterance_seconds=float(
                os.getenv("JENEFAR_VOICE_MAX_UTTERANCE_SECONDS", "12")
            ),
        )
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=30)
        self._speaking = False
        self._buffers: list[np.ndarray] = []
        self._silence_started: float | None = None

    @staticmethod
    def _rms(chunk: np.ndarray) -> float:
        data = chunk.astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0

    def _callback(self, indata, frames, time_info, status) -> None:
        if self._stop.is_set():
            return
        if status:
            print(f"[JENEFAR] Audio: {status}")
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
            # Drop the oldest pending block rather than growing memory forever.
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._audio_queue.put_nowait(indata.copy())
            except queue.Full:
                pass

    def _reset_utterance(self) -> None:
        self._speaking = False
        self._buffers = []
        self._silence_started = None

    def _consume_block(self, chunk: np.ndarray) -> bytes | None:
        now = time.monotonic()
        rms = self._rms(chunk)
        started = self._speaking

        if not self._speaking:
            if rms < self.config.start_threshold:
                return None
            self._speaking = True
            self._buffers = [chunk]
            self._silence_started = None
            return None

        self._buffers.append(chunk)
        elapsed = (len(self._buffers) * len(chunk)) / self.config.sample_rate

        if rms >= self.config.stop_threshold:
            self._silence_started = None
        elif self._silence_started is None:
            self._silence_started = now

        silence_elapsed = (
            0.0
            if self._silence_started is None
            else now - self._silence_started
        )

        if silence_elapsed * 1000 >= self.config.silence_ms or elapsed >= self.config.max_utterance_seconds:
            pcm = np.concatenate(self._buffers).astype(np.int16).tobytes()
            self._reset_utterance()
            return pcm

        # Keep the local variable useful for debugging and future metrics.
        _ = started
        return None

    @staticmethod
    def _wav_bytes(pcm: bytes, sample_rate: int, channels: int) -> io.BytesIO:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        output.seek(0)
        output.name = "jenefar_utterance.wav"
        return output

    async def _transcribe(self, pcm: bytes) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        audio = self._wav_bytes(
            pcm,
            self.config.sample_rate,
            self.config.channels,
        )
        result = await client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe"),
            file=audio,
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

    async def _process_utterance(self, pcm: bytes) -> None:
        try:
            text = await self._transcribe(pcm)
        except Exception as exc:
            print(f"[JENEFAR] STT error: {type(exc).__name__}: {exc}")
            return

        if not text:
            return

        print(f"[USER/STT] {text}")
        if self.avatar is not None:
            self.avatar.publish("listening", text)

        lowered = text.lower().strip()
        if lowered == "exit":
            self._stop.set()
            return

        if self.orchestrator.state.name == "SLEEPING":
            if not self.orchestrator.wakeword.detect(text):
                return
            command = self.orchestrator.wakeword.remove_wake_phrase(text)
            if not command:
                reply = "Yes, I'm listening."
            else:
                reply = self.orchestrator.handle(command)
        else:
            reply = self.orchestrator.handle(text)

        print(f"[JENEFAR] {reply}")
        if self.avatar is not None:
            self.avatar.publish("speaking", reply)
        try:
            await self._speak(reply)
        except Exception as exc:
            print(f"[JENEFAR] TTS error: {type(exc).__name__}: {exc}")
        finally:
            if self.avatar is not None:
                self.avatar.publish("idle", "")

    async def run_async(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            print("[JENEFAR] Set OPENAI_API_KEY before using continuous voice mode.")
            return

        try:
            import sounddevice as sd
        except ImportError as exc:
            print(f"[JENEFAR] sounddevice is required: {exc}")
            return

        blocksize = int(self.config.sample_rate * self.config.block_ms / 1000)
        print("[JENEFAR] Continuous voice mode started.")
        print("[JENEFAR] Say 'Hi Jenefar' or 'Hello Jenefar' to wake me.")
        print("[JENEFAR] Say 'exit' to stop.")

        try:
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype="int16",
                blocksize=blocksize,
                callback=self._callback,
            ):
                while not self._stop.is_set():
                    try:
                        chunk = await asyncio.to_thread(
                            self._audio_queue.get,
                            True,
                            0.25,
                        )
                    except queue.Empty:
                        continue

                    pcm = self._consume_block(chunk)
                    if pcm:
                        await self._process_utterance(pcm)
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            print(f"[JENEFAR] Continuous voice error: {type(exc).__name__}: {exc}")
        finally:
            self._stop.set()
            self._reset_utterance()

        print("[JENEFAR] Continuous voice mode stopped.")

    def run(self) -> None:
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            self._stop.set()
            print("\n[JENEFAR] Continuous voice mode stopped.")
