from __future__ import annotations

import asyncio
import io
import math
import os
import queue
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass

import numpy as np

from jenefar.voice.provider import ProviderVoiceRuntime
from jenefar.voice.wakeword_engine import WakeWordEngine


@dataclass(frozen=True)
class VoiceConfig:
    sample_rate: int = 16_000
    channels: int = 1
    block_ms: int = 50
    start_threshold: float = 0.025
    stop_threshold: float = 0.014
    silence_ms: int = 1100
    max_utterance_seconds: float = 10.0


class ContinuousVoiceRuntime:
    """Calibrated phrase capture -> STT -> orchestrator -> TTS runtime.

    Uses sounddevice for microphone capture so it does not require PyAudio.
    SpeechRecognition is used only for its Google recognition adapter, with
    Jenefar's provider STT as the fallback.
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
                os.getenv("JENEFAR_VOICE_MAX_UTTERANCE_SECONDS", "10")
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
        self._conversation_language: str | None = None
        self._ambient_threshold = self.config.start_threshold
        self._legacy_ready = False

    @staticmethod
    def _rms(chunk: np.ndarray) -> float:
        data = chunk.astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0

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

    def _callback(self, indata, frames, time_info, status) -> None:
        if self._stop.is_set():
            return
        if status:
            print(f"[JENEFAR] Audio: {status}")
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
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

        silence_elapsed = 0.0 if self._silence_started is None else now - self._silence_started
        if (
            silence_elapsed * 1000 >= self.config.silence_ms
            or elapsed >= self.config.max_utterance_seconds
        ):
            pcm = np.concatenate(self._buffers).astype(np.int16).tobytes()
            self._reset_utterance()
            if self._wakeword.available:
                self._wake_triggered = False
            return pcm
        return None

    def _calibrate_microphone(self) -> None:
        import sounddevice as sd

        blocksize = int(self.config.sample_rate * self.config.block_ms / 1000)
        duration = float(os.getenv("JENEFAR_LEGACY_AMBIENT_SECONDS", "0.7"))
        samples: list[float] = []
        with sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            blocksize=blocksize,
        ) as stream:
            end_at = time.monotonic() + max(0.2, duration)
            while time.monotonic() < end_at:
                chunk, _overflowed = stream.read(blocksize)
                samples.append(self._rms(np.asarray(chunk)))
        ambient = float(np.mean(samples)) if samples else 0.0
        self._ambient_threshold = max(
            self.config.start_threshold,
            ambient * float(os.getenv("JENEFAR_VOICE_AMBIENT_MULTIPLIER", "2.2"))
            + float(os.getenv("JENEFAR_VOICE_AMBIENT_OFFSET", "0.006")),
        )
        self._legacy_ready = True
        print(
            f"[JENEFAR] Mic calibrated: ambient={ambient:.4f}, "
            f"speech_threshold={self._ambient_threshold:.4f}"
        )

    def _capture_phrase_pcm(self) -> bytes | None:
        import sounddevice as sd

        blocksize = int(self.config.sample_rate * self.config.block_ms / 1000)
        timeout = float(os.getenv("JENEFAR_LEGACY_LISTEN_TIMEOUT", "5"))
        phrase_limit = float(os.getenv("JENEFAR_LEGACY_PHRASE_LIMIT", "10"))
        silence_after_phrase = float(
            os.getenv("JENEFAR_LEGACY_PAUSE_THRESHOLD", "0.8")
        )
        pre_roll_blocks = max(1, int(0.25 * self.config.sample_rate / blocksize))
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_blocks)
        buffers: list[np.ndarray] = []
        started_at: float | None = None
        silence_started: float | None = None
        deadline = time.monotonic() + timeout

        with sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            blocksize=blocksize,
        ) as stream:
            while time.monotonic() < deadline and not self._stop.is_set():
                chunk, _overflowed = stream.read(blocksize)
                chunk = np.asarray(chunk, dtype=np.int16)
                rms = self._rms(chunk)
                now = time.monotonic()
                if started_at is None:
                    pre_roll.append(chunk)
                    if rms >= self._ambient_threshold:
                        started_at = now
                        buffers = list(pre_roll)
                        buffers.append(chunk)
                    continue

                buffers.append(chunk)
                elapsed = now - started_at
                if rms >= self.config.stop_threshold:
                    silence_started = None
                elif silence_started is None and elapsed >= 0.5:
                    silence_started = now

                if (
                    silence_started is not None
                    and now - silence_started >= silence_after_phrase
                ) or elapsed >= phrase_limit:
                    return np.concatenate(buffers).astype(np.int16).tobytes()

        return None

    @staticmethod
    def _google_transcribe(pcm: bytes, sample_rate: int) -> str:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        audio = sr.AudioData(pcm, sample_rate, 2)
        try:
            return str(
                recognizer.recognize_google(
                    audio,
                    language=os.getenv("JENEFAR_LEGACY_STT_LANGUAGE", "hi-IN"),
                )
            ).strip()
        except (sr.UnknownValueError, sr.RequestError):
            return ""

    async def _transcribe_phrase(self, pcm: bytes) -> str:
        text = await asyncio.to_thread(self._google_transcribe, pcm, self.config.sample_rate)
        if text:
            return text
        return await self._voice.transcribe_pcm(
            pcm,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
        )

    async def _transcribe(self, pcm: bytes) -> str:
        return await self._transcribe_phrase(pcm)

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

        if normalized.strip() == "exit":
            print("[USER/STT] exit")
            self._stop.set()
            return

        if self.orchestrator.state.name == "SLEEPING":
            matched_phrase = self.orchestrator.wakeword.matched_phrase(text)
            if matched_phrase is None:
                return
            command = self.orchestrator.wakeword.remove_wake_phrase(text)
            if matched_phrase == "hello jenefar":
                self._conversation_language = "Hinglish"
            response_language = self._conversation_language or "Hinglish"
            print(f"[USER/STT] {text}")
            if self.avatar is not None:
                self.avatar.publish("listening", text)
            if not command:
                reply = (
                    "Haan, boliye. Main sun rahi hoon."
                    if response_language == "Hinglish"
                    else "Yes, I'm listening."
                )
            else:
                reply = self.orchestrator.handle(
                    command,
                    response_language=response_language,
                )
        else:
            print(f"[USER/STT] {text}")
            if self.avatar is not None:
                self.avatar.publish("listening", text)
            reply = self.orchestrator.handle(
                text,
                response_language=self._conversation_language,
            )

        self._last_transcript = normalized
        self._last_transcript_at = now
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

        try:
            import sounddevice as sd
        except ImportError as exc:
            print(f"[JENEFAR] sounddevice is required: {exc}")
            return

        stt = status["stt"]
        tts = status["tts"]
        print(
            f"[JENEFAR] Continuous voice providers: "
            f"STT={stt['provider']}/{stt['model']} "
            f"fallback={','.join(stt.get('fallback', [])) or 'none'}; "
            f"TTS={tts['provider']+'/'+tts['model'] if tts else 'unavailable'} "
            f"fallback={','.join(tts.get('fallback', [])) if tts else 'none'}"
        )
        print(
            f"[JENEFAR] Microphone: {self.config.sample_rate} Hz, "
            f"threshold={self.config.start_threshold:.4f}, "
            f"silence={self.config.silence_ms}ms"
        )

        try:
            await asyncio.to_thread(self._calibrate_microphone)
        except Exception as exc:
            print(
                f"[JENEFAR] Calibrated phrase capture unavailable; "
                f"using VAD fallback: {type(exc).__name__}: {exc}"
            )
            self._legacy_ready = False

        print("[JENEFAR] Continuous voice mode started.")
        print("[JENEFAR] Say 'Hi Jenefar' or 'Hello Jenefar' to wake me.")
        print("[JENEFAR] Say 'exit' to stop.")

        try:
            while not self._stop.is_set():
                if self._legacy_ready:
                    pcm = await asyncio.to_thread(self._capture_phrase_pcm)
                    if pcm:
                        await self._process_utterance(pcm)
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
                        break
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
            print("
[JENEFAR] Continuous voice mode stopped.")
