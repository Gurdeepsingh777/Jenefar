from __future__ import annotations

import asyncio
import io
import math
import os
import queue
import threading
import time
import wave
from dataclasses import dataclass

import numpy as np

from jenefar.voice.provider import ProviderVoiceRuntime
from jenefar.voice.wakeword_engine import WakeWordEngine


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
            sample_rate=int(os.getenv("JENEFAR_VOICE_SAMPLE_RATE", "16000")),
            block_ms=int(os.getenv("JENEFAR_VOICE_BLOCK_MS", "50")),
            start_threshold=float(os.getenv("JENEFAR_VOICE_START_THRESHOLD", "0.025")),
            stop_threshold=float(os.getenv("JENEFAR_VOICE_STOP_THRESHOLD", "0.014")),
            silence_ms=int(os.getenv("JENEFAR_VOICE_SILENCE_MS", "1100")),
            max_utterance_seconds=float(
                os.getenv("JENEFAR_VOICE_MAX_UTTERANCE_SECONDS", "12")
            ),
        )
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=30)
        self._speaking = False
        self._buffers: list[np.ndarray] = []
        self._silence_started: float | None = None
        self._wakeword = WakeWordEngine.from_environment()
        self._wake_triggered = not self._wakeword.available
        self._voice = ProviderVoiceRuntime(orchestrator, avatar=avatar)
        self._processing_utterance = False
        self._last_transcript = ""
        self._last_transcript_at = 0.0
        self._transcript_repeat_window = float(
            os.getenv("JENEFAR_VOICE_TRANSCRIPT_REPEAT_WINDOW", "2.5")
        )
        self._conversation_language = None
        self._legacy_listener = None

    def _try_init_legacy_listener(self):
        if os.getenv("JENEFAR_DISABLE_LEGACY_LISTENER", "").strip().lower() in {"1", "true", "yes"}:
            return None
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = float(os.getenv("JENEFAR_LEGACY_PAUSE_THRESHOLD", "0.8"))
            recognizer.non_speaking_duration = 0.5
            microphone = sr.Microphone()
            with microphone as source:
                recognizer.adjust_for_ambient_noise(
                    source,
                    duration=float(os.getenv("JENEFAR_LEGACY_AMBIENT_SECONDS", "0.7")),
                )
            return recognizer, microphone
        except Exception as exc:
            print(f"[JENEFAR] Phrase listener unavailable; using VAD: {type(exc).__name__}: {exc}")
            return None

    def _legacy_capture_once(self) -> str:
        if not self._legacy_listener:
            return ""
        recognizer, microphone = self._legacy_listener
        try:
            import speech_recognition as sr
            with microphone as source:
                audio = recognizer.listen(
                    source,
                    timeout=float(os.getenv("JENEFAR_LEGACY_LISTEN_TIMEOUT", "5")),
                    phrase_time_limit=float(os.getenv("JENEFAR_LEGACY_PHRASE_LIMIT", "10")),
                )
            try:
                return str(
                    recognizer.recognize_google(
                        audio,
                        language=os.getenv("JENEFAR_LEGACY_STT_LANGUAGE", "hi-IN"),
                    )
                ).strip()
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as exc:
                print(f"[JENEFAR] Legacy STT service error: {exc}")
                return ""
        except Exception:
            return ""

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

        if not self._wake_triggered:
            detected, _score = self._wakeword.process(
                chunk,
                sample_rate=self.config.sample_rate,
            )
            if not detected:
                return None
            self._wake_triggered = True
            if self.avatar is not None:
                self.avatar.publish("listening", "Wake word detected", level=0.12)
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
        if elapsed < 0.8:
            return None

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
            if self._wakeword.available:
                self._wake_triggered = False
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
        if self._legacy_listener:
            captured = await asyncio.to_thread(self._legacy_capture_once)
            if captured:
                return captured
        return await self._voice.transcribe_pcm(
            pcm,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
        )

    async def _animate_speaking(self, text: str) -> None:
        if self.avatar is None:
            return

        duration = max(0.8, len(text.split()) * 0.24)
        started = time.monotonic()

        while True:
            elapsed = time.monotonic() - started
            phase = (elapsed / duration) * 20.0
            level = 0.10 + 0.72 * ((0.5 + 0.5 * math.sin(phase)) ** 1.7)
            self.avatar.publish("speaking", text, level=level)
            await asyncio.sleep(0.09)

    async def _speak(self, text: str) -> None:
        await self._voice.speak(text)

    async def _process_utterance(self, pcm: bytes) -> None:
        if self._processing_utterance:
            return
        self._processing_utterance = True
        try:
            text = await self._transcribe(pcm)
            if text:
                await self._process_transcript(text)
        except Exception as exc:
            print(f"[JENEFAR] Voice processing error: {type(exc).__name__}: {exc}")
        finally:
            self._processing_utterance = False

    async def _process_transcript(self, text: str) -> None:
        normalized = self.orchestrator.wakeword.normalize_stt_text(text)
        now = time.monotonic()
        if (
            normalized
            and normalized == self._last_transcript
            and now - self._last_transcript_at < self._transcript_repeat_window
        ):
            return
        self._last_transcript = normalized
        self._last_transcript_at = now

        lowered = normalized.strip()
        if not lowered:
            return
        if lowered == "exit":
            self._stop.set()
            return

        print(f"[USER/STT] {text}")
        if self.avatar is not None:
            self.avatar.publish("listening", text)

        if self.orchestrator.state.name == "SLEEPING":
            matched_phrase = self.orchestrator.wakeword.matched_phrase(text)
            if matched_phrase is None:
                return
            command = self.orchestrator.wakeword.remove_wake_phrase(text)
            if matched_phrase == "hello jenefar":
                self._conversation_language = "Hinglish"
            response_language = self._conversation_language or "Hinglish"
            if not command:
                reply = "Haan, boliye. Main sun rahi hoon." if response_language == "Hinglish" else "Yes, I'm listening."
            else:
                reply = self.orchestrator.handle(command, response_language=response_language)
        else:
            reply = self.orchestrator.handle(
                text,
                response_language=self._conversation_language,
            )

        print(f"[JENEFAR] {reply}")
        try:
            await self._speak(reply)
        except Exception as exc:
            print(f"[JENEFAR] TTS error: {type(exc).__name__}: {exc}")
            self._voice.reset_audio_health()
        finally:
            if self.avatar is not None:
                self.avatar.publish("idle", "")

    async def run_async(self) -> None:
        status = self._voice.audio_status()
        if not status["stt"]:
            print("[JENEFAR] Continuous voice requires at least one configured STT provider.")
            print("[JENEFAR] Set OPENAI_API_KEY or GROQ_API_KEY.")
            return
        print(
            f"[JENEFAR] Continuous voice providers: "
            f"STT={status['stt']['provider']}/{status['stt']['model']} "
            f"fallback={','.join(status['stt'].get('fallback', [])) or 'none'}; "
            f"TTS={status['tts']['provider']+'/'+status['tts']['model'] if status['tts'] else 'unavailable'} "
            f"fallback={','.join(status['tts'].get('fallback', [])) if status['tts'] else 'none'}"
        )

        try:
            import sounddevice as sd
            print(
                f"[JENEFAR] Microphone: {self.config.sample_rate} Hz, "
                f"threshold={self.config.start_threshold:.4f}, "
                f"silence={self.config.silence_ms}ms"
            )
        except ImportError as exc:
            print(f"[JENEFAR] sounddevice is required: {exc}")
            return

        self._legacy_listener = await asyncio.to_thread(self._try_init_legacy_listener)
        if self._legacy_listener:
            print("[JENEFAR] Voice capture: calibrated phrase listener.")
        else:
            print("[JENEFAR] Voice capture: VAD fallback.")
        print("[JENEFAR] Continuous voice mode started.")
        print("[JENEFAR] Say 'Hi Jenefar' or 'Hello Jenefar' to wake me.")
        print("[JENEFAR] Say 'exit' to stop.")

        try:
            if self._legacy_listener:
                while not self._stop.is_set():
                    text = await asyncio.to_thread(self._legacy_capture_once)
                    if text:
                        await self._process_transcript(text)
            else:
                blocksize = int(self.config.sample_rate * self.config.block_ms / 1000)
                with sd.InputStream(
                    samplerate=self.config.sample_rate,
                    channels=self.config.channels,
                    dtype="int16",
                    blocksize=blocksize,
                    callback=self._callback,
                ):
                    while not self._stop.is_set():
                        try:
                            chunk = await asyncio.to_thread(self._audio_queue.get, True, 0.25)
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
