from __future__ import annotations

import asyncio
import base64
import io
import math
import os
import shutil
import tempfile
import threading
import time
import wave
from pathlib import Path
import subprocess

from jenefar.core.provider_pool import ProviderPool, is_retryable_provider_error
from jenefar.voice.speech import enforce_hinglish


class ProviderVoiceRuntime:
    """Provider-aware microphone -> STT -> agent -> TTS runtime with audio failover."""

    def __init__(self, orchestrator, seconds: int = 8, avatar=None):
        self.orchestrator = orchestrator
        self.seconds = seconds
        self.avatar = avatar
        self._audio_pool = ProviderPool()
        self._local_stt_model = None
        self._local_stt_signature = None
        self._local_stt_load_lock = threading.Lock()
        self._local_stt_inference_lock = threading.Lock()

    @staticmethod
    def _direct_openai_key() -> str:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return "" if not key or key.startswith("sk-or-") else key

    @staticmethod
    def _direct_gemini_key() -> str:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if key:
            return key
        base_url = (
            os.getenv("LLM_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
        ).lower()
        if "generativelanguage.googleapis.com" in base_url:
            return (
                os.getenv("LLM_API_KEY", "").strip()
                or os.getenv("API_KEY", "").strip()
            )
        return ""

    @classmethod
    def _configured_audio_providers(cls) -> list[str]:
        raw = os.getenv("JENEFAR_VOICE_PROVIDER_ORDER", "groq,openai")
        requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
        ordered = requested or ["groq", "openai"]
        ordered = [name for name in ordered if name in ("openai", "groq", "gemini")]
        # Older .env files only list Groq/OpenAI. Automatically append Gemini when
        # its key is configured so an exhausted OpenAI quota cannot disable voice.
        if "gemini" not in ordered:
            ordered.append("gemini")
        return [name for name in ordered if cls._provider_configured(name)]

    @classmethod
    def _provider_configured(cls, name: str) -> bool:
        if name == "openai":
            return bool(cls._direct_openai_key())
        if name == "groq":
            return bool(os.getenv("GROQ_API_KEY", "").strip())
        if name == "gemini":
            return bool(cls._direct_gemini_key())
        return False

    @staticmethod
    def _native_tts_enabled() -> bool:
        return os.getenv("JENEFAR_ENABLE_NATIVE_TTS", "").strip().lower() in {
            "1", "true", "yes"
        }

    @classmethod
    def audio_status(cls) -> dict[str, dict | None]:
        stt_providers = cls._configured_audio_providers()
        tts_providers = []
        native_tts = cls._native_tts_enabled()
        if native_tts and cls._legacy_edge_tts_available():
            tts_providers.append("edge")
        tts_providers.extend(
            name for name in stt_providers
            if cls._tts_configured(name)
        )
        if native_tts and cls._local_espeak_available():
            tts_providers.append("espeak")
        if (
            native_tts
            and shutil.which("piper")
            and os.getenv("JENEFAR_LOCAL_TTS_MODEL", "").strip()
        ):
            tts_providers.append("local")
        result: dict[str, dict | None] = {"stt": None, "tts": None}

        if stt_providers:
            result["stt"] = {
                "provider": stt_providers[0],
                "model": cls._stt_model(stt_providers[0]),
                "fallback": stt_providers[1:],
            }
        if tts_providers:
            result["tts"] = {
                "provider": tts_providers[0],
                "model": cls._tts_model(tts_providers[0]),
                "fallback": tts_providers[1:],
            }
        return result

    @staticmethod
    def _legacy_edge_tts_available() -> bool:
        try:
            import edge_tts  # noqa: F401
        except Exception:
            return False
        return bool(shutil.which("mpv") or shutil.which("ffplay"))

    @staticmethod
    def _local_espeak_available() -> bool:
        return bool(shutil.which("espeak-ng") or shutil.which("espeak"))

    @classmethod
    def _tts_configured(cls, provider: str) -> bool:
        if provider == "openai":
            return bool(cls._direct_openai_key())
        if provider == "groq":
            disabled = os.getenv("JENEFAR_DISABLE_GROQ_TTS", "").strip().lower()
            return bool(os.getenv("GROQ_API_KEY", "").strip()) and disabled not in {
                "1", "true", "yes"
            }
        if provider == "edge":
            return cls._legacy_edge_tts_available()
        if provider == "espeak":
            return cls._local_espeak_available()
        if provider == "local":
            return bool(shutil.which("piper") and os.getenv("JENEFAR_LOCAL_TTS_MODEL", "").strip())
        return False

    @staticmethod
    def _stt_model(provider: str) -> str:
        if provider == "openai":
            return os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
        if provider == "groq":
            return os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
        base_url = (
            os.getenv("LLM_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
        ).lower()
        configured_model = (
            os.getenv("JENEFAR_GEMINI_STT_MODEL", "").strip()
            or os.getenv("GEMINI_MODEL", "").strip()
        )
        if not configured_model and "generativelanguage.googleapis.com" in base_url:
            configured_model = os.getenv("LLM_MODEL_NAME", "").strip()
        return configured_model or "gemini-3.8-flash"

    @staticmethod
    def _tts_model(provider: str) -> str:
        if provider == "edge":
            return os.getenv("JENEFAR_EDGE_TTS_VOICE", "en-IN-NeerjaNeural")
        if provider == "espeak":
            return "system-espeak"
        if provider == "local":
            return os.getenv("JENEFAR_LOCAL_TTS_MODEL", "piper")
        return (
            os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
            if provider == "openai"
            else os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
        )

    def _provider_order(self) -> list[str]:
        # Use the same compatibility path as startup capability reporting.
        return self._configured_audio_providers()

    def _tts_provider_order(self) -> list[str]:
        """Return configured TTS providers; native playback is explicit opt-in."""
        order = []
        native_tts = self._native_tts_enabled()
        if native_tts and self._legacy_edge_tts_available():
            order.append("edge")
        order.extend(
            name
            for name in self._provider_order()
            if self._tts_configured(name)
        )
        if (
            native_tts
            and shutil.which("piper")
            and os.getenv("JENEFAR_LOCAL_TTS_MODEL", "").strip()
        ):
            order.append("local")
        return order

    @staticmethod
    def _wav_bytes(
        pcm: bytes,
        sample_rate: int = 16_000,
        channels: int = 1,
    ) -> io.BytesIO:
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
    def _local_stt_model_spec() -> str:
        """Return a Whisper model path or a Hugging Face cache model alias."""
        path = os.getenv("JENEFAR_LOCAL_STT_MODEL_PATH", "").strip()
        model = os.getenv("JENEFAR_LOCAL_STT_MODEL", "small").strip()
        return str(Path(path).expanduser()) if path else (model or "small")

    @staticmethod
    def _local_stt_model_candidates(model_spec: str, *, explicit_path: bool = False) -> list[str]:
        """Try the configured Whisper alias, then smaller aliases that may be cached."""
        if explicit_path:
            return [model_spec]
        ranks = {"tiny": 0, "base": 1, "small": 2, "medium": 3, "large": 4}
        configured = str(model_spec or "base").strip()
        if configured not in ranks:
            return [configured]
        smaller = [
            name for name, rank in ranks.items()
            if rank < ranks[configured]
        ]
        smaller.sort(key=lambda name: ranks[name], reverse=True)
        return list(dict.fromkeys([configured, *smaller]))

    def _get_local_stt_model(self):
        """Load cache-only Whisper, falling back to a smaller cached model."""
        model_spec = self._local_stt_model_spec()
        explicit_path = bool(os.getenv("JENEFAR_LOCAL_STT_MODEL_PATH", "").strip())
        device = os.getenv("JENEFAR_LOCAL_STT_DEVICE", "cpu").strip().lower() or "cpu"
        default_compute = "int8" if device == "cpu" else "float16"
        compute_type = os.getenv(
            "JENEFAR_LOCAL_STT_COMPUTE_TYPE", default_compute
        ).strip() or default_compute
        signature = (model_spec, device, compute_type)

        with self._local_stt_load_lock:
            if self._local_stt_model is not None and self._local_stt_signature == signature:
                return self._local_stt_model
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Local Whisper STT is not installed. Run "
                    "'python run.py --setup-voice' in the active .venv while online; "
                    "the setup command installs faster-whisper and caches a small offline model."
                ) from exc

            if explicit_path and not Path(model_spec).is_dir():
                raise RuntimeError(
                    f"JENEFAR_LOCAL_STT_MODEL_PATH does not point to a model directory: {model_spec}"
                )

            candidates = self._local_stt_model_candidates(
                model_spec,
                explicit_path=explicit_path,
            )
            failures: list[str] = []
            model = None
            selected_model = ""
            for candidate in candidates:
                try:
                    model = WhisperModel(
                        candidate,
                        device=device,
                        compute_type=compute_type,
                        local_files_only=True,
                    )
                    selected_model = candidate
                    break
                except Exception as exc:
                    failures.append(f"{candidate}: {type(exc).__name__}: {exc}")

            if model is None:
                detail = "; ".join(failures[-3:])
                raise RuntimeError(
                    "No usable local Whisper model was found in the cache. "
                    f"Tried: {', '.join(candidates)}. "
                    "While online, run 'python run.py --setup-voice' once to cache the "
                    "base multilingual model; microphone transcription then works offline. "
                    + detail
                )

            self._local_stt_model = model
            self._local_stt_signature = signature
            print(
                f"[JENEFAR] Local Whisper STT ready: {selected_model} "
                f"({device}/{compute_type}, cache-only)."
            )
            if selected_model != model_spec:
                print(
                    f"[JENEFAR] Configured Whisper model '{model_spec}' was not cached; "
                    f"using smaller cached model '{selected_model}'."
                )
            return model

    async def _transcribe_local(self, audio) -> str:
        """Transcribe a WAV buffer with cached Whisper, retrying without VAD.

        VAD can discard quiet Hinglish syllables or short commands. If the
        filtered pass produces no text, replay the same in-memory audio without
        VAD and with a wider beam before reporting failure to the browser.
        """
        def run() -> str:
            with self._local_stt_inference_lock:
                model = self._get_local_stt_model()
                configured_language = os.getenv(
                    "JENEFAR_LOCAL_STT_LANGUAGE", "auto"
                ).strip().lower()
                language = None if configured_language in {"", "auto"} else configured_language
                attempts = [
                    {"language": language, "beam_size": 1, "vad_filter": True},
                    {"language": language, "beam_size": 3, "vad_filter": False},
                ]
                # Auto-detection can miss short Hindi/Hinglish utterances. When
                # language is auto, give the cached model one explicit Hindi pass
                # before telling the user that speech was not recognized.
                if language is None:
                    attempts.append(
                        {"language": "hi", "beam_size": 3, "vad_filter": False}
                    )

                failures: list[str] = []
                for attempt_number, options in enumerate(attempts, start=1):
                    audio.seek(0)
                    try:
                        segments, _info = model.transcribe(
                            audio,
                            language=options["language"],
                            beam_size=options["beam_size"],
                            vad_filter=options["vad_filter"],
                            temperature=0.0,
                            condition_on_previous_text=False,
                        )
                        transcript = " ".join(
                            str(segment.text or "").strip()
                            for segment in segments
                            if str(segment.text or "").strip()
                        ).strip()
                    except Exception as exc:
                        failures.append(f"pass {attempt_number}: {type(exc).__name__}: {exc}")
                        continue
                    if transcript:
                        if attempt_number > 1:
                            print(
                                "[JENEFAR] Local Whisper recovered speech on fallback "
                                f"pass {attempt_number} (language={options['language'] or 'auto'}, "
                                f"vad_filter={options['vad_filter']})."
                            )
                        return transcript
                    failures.append(
                        f"pass {attempt_number}: no speech text "
                        f"(language={options['language'] or 'auto'}, "
                        f"vad_filter={options['vad_filter']}, beam_size={options['beam_size']})"
                    )

                detail = "; ".join(failures)
                raise RuntimeError(
                    "Local Whisper loaded, but no transcript was produced from the captured audio. "
                    "Check the selected microphone/input level, speak a little closer, and try a "
                    "short 2–4 second phrase. " + detail
                )

        return await asyncio.to_thread(run)

    def _cooldown_seconds(self, exc: Exception) -> float:
        message = str(exc).lower()
        if any(marker in message for marker in (
            "insufficient_quota", "credit_balance_exhausted",
            "resource_exhausted", "quota exceeded",
        )):
            return float(os.getenv("JENEFAR_VOICE_QUOTA_COOLDOWN_SECONDS", "3600"))
        return float(os.getenv("JENEFAR_PROVIDER_COOLDOWN_SECONDS", "60"))

    def _mark_failed_provider(self, provider: str, exc: Exception) -> None:
        self._audio_pool.cooldown(provider, self._cooldown_seconds(exc))

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
        async with AsyncOpenAI(api_key=ProviderVoiceRuntime._direct_openai_key()) as client:
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

    @staticmethod
    async def _transcribe_gemini(audio: io.BytesIO) -> str:
        """Transcribe audio with Gemini when OpenAI/Groq STT is unavailable."""
        import httpx

        api_key = ProviderVoiceRuntime._direct_gemini_key()
        if not api_key:
            raise RuntimeError("Gemini STT is not configured.")
        audio.seek(0)
        encoded_audio = base64.b64encode(audio.read()).decode("ascii")
        model = ProviderVoiceRuntime._stt_model("gemini")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Transcribe only the speech in this audio. Return only the words "
                                "spoken, with no explanation or labels. Preserve the original "
                                "language and meaning, including Hindi, Hinglish, or English; do "
                                "not translate or add words. For Hindi/Hinglish, prefer Roman "
                                "script when the speaker uses Roman Hinglish."
                            )
                        },
                        {
                            "inlineData": {
                                "mimeType": "audio/wav",
                                "data": encoded_audio,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"maxOutputTokens": 1024},
        }
        timeout = float(os.getenv("JENEFAR_GEMINI_STT_TIMEOUT", "35"))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={"x-goog-api-key": api_key},
                json=payload,
            )
        if response.status_code >= 400:
            try:
                error_body = response.json()
                detail = str(error_body.get("error", {}).get("message", "")).strip()
            except Exception:
                detail = ""
            error = RuntimeError(
                f"Gemini STT HTTP {response.status_code}"
                + (f": {detail[:400]}" if detail else "")
            )
            error.status_code = response.status_code
            raise error
        try:
            body = response.json()
            parts = body["candidates"][0]["content"]["parts"]
            transcript = " ".join(
                str(part.get("text", "")).strip()
                for part in parts
                if isinstance(part, dict) and str(part.get("text", "")).strip()
            ).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Gemini STT returned an invalid response.") from exc
        # Empty text is a provider-level miss, not a terminal error.
        # transcribe_pcm() will try the next cloud provider and local Whisper.
        return transcript

    async def transcribe_pcm(
        self, pcm: bytes, *, sample_rate: int = 16_000, channels: int = 1
    ) -> str:
        audio = self._wav_bytes(pcm, sample_rate=sample_rate, channels=channels)
        providers = self._provider_order()
        last_error: Exception | None = None
        for provider in providers:
            if provider == "gemini":
                # ProviderPool's native Gemini key is GEMINI_API_KEY; voice also
                # supports the Telegram agent's LLM_API_KEY alias for Google URLs.
                available = self._provider_configured(provider) and (
                    time.monotonic() >= self._audio_pool.cooldowns.get(provider, 0.0)
                )
            else:
                available = self._audio_pool.available(provider)
            if not available:
                continue
            try:
                if provider == "openai":
                    transcript = await self._transcribe_openai(audio)
                elif provider == "groq":
                    transcript = await self._transcribe_groq(audio)
                elif provider == "gemini":
                    transcript = await self._transcribe_gemini(audio)
                else:
                    continue

                transcript = str(transcript or "").strip()
                if transcript:
                    return transcript

                # A successful HTTP response can still contain no recognized
                # words. Do not treat that as success: continue to the next
                # provider, then the cache-only local Whisper fallback below.
                last_error = RuntimeError(f"{provider} STT returned an empty transcript.")
                print(
                    f"[JENEFAR] STT provider {provider} returned an empty transcript; "
                    "trying the next configured provider."
                )
            except Exception as exc:
                last_error = exc
                if not is_retryable_provider_error(exc):
                    raise
                self._mark_failed_provider(provider, exc)
                print(
                    f"[JENEFAR] STT provider {provider} failed; "
                    f"trying the next configured provider: {type(exc).__name__}: {exc}"
                )

        # Always attempt local speech recognition last. It is cache-only, so it
        # never attempts a model download while the user is speaking.
        try:
            # Keep the transcriber contract normalized across cloud and local
            # providers; whitespace-only or padded output must not be forwarded
            # as a successful command transcript.
            return str(await self._transcribe_local(audio) or "").strip()
        except Exception as local_error:
            local_detail = f"{type(local_error).__name__}: {local_error}"
            if last_error is not None:
                raise RuntimeError(
                    "All configured STT providers failed and local Whisper fallback is unavailable. "
                    f"Local STT detail: {local_detail}"
                ) from local_error
            if providers:
                raise RuntimeError(
                    "No currently available STT provider. "
                    f"Local Whisper fallback is unavailable: {local_detail}"
                ) from local_error
            raise RuntimeError(
                "No cloud STT provider is configured and local Whisper fallback is unavailable. "
                f"Local STT detail: {local_detail}"
            ) from local_error

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

    async def _speak_local(self, text: str) -> None:
        """Local neural TTS fallback via Piper CLI when available."""
        import shutil
        import subprocess

        piper = shutil.which("piper")
        if not piper:
            raise RuntimeError("Local Piper TTS is not installed.")
        model = os.getenv("JENEFAR_LOCAL_TTS_MODEL", "").strip()
        if not model:
            raise RuntimeError(
                "JENEFAR_LOCAL_TTS_MODEL is not configured for local Piper TTS."
            )
        with tempfile.NamedTemporaryFile(
            suffix=".wav", prefix="jenefar_local_tts_", delete=False
        ) as tmp:
            output_path = tmp.name
        animation = asyncio.create_task(self._animate_speaking(text)) if self.avatar else None
        try:
            process = await asyncio.to_thread(
                subprocess.run,
                [piper, "--model", model, "--output_file", output_path],
                input=text,
                text=True,
                capture_output=True,
                check=False,
                timeout=45,
            )
            if process.returncode != 0:
                raise RuntimeError(
                    f"Local Piper TTS failed: {process.stderr.strip() or process.returncode}"
                )
            await asyncio.to_thread(self._play_wav, output_path)
        finally:
            if animation is not None:
                animation.cancel()
                try:
                    await animation
                except asyncio.CancelledError:
                    pass
            try:
                os.unlink(output_path)
            except FileNotFoundError:
                pass

    async def _speak_edge(self, text: str) -> None:
        """Legacy edge-tts -> mpv/ffplay playback path."""
        import edge_tts

        voice = os.getenv("JENEFAR_EDGE_TTS_VOICE", "en-IN-NeerjaNeural").strip()
        player = shutil.which("mpv") or shutil.which("ffplay")
        if not player:
            raise RuntimeError("edge-tts requires mpv or ffplay.")

        animation = asyncio.create_task(self._animate_speaking(text)) if self.avatar else None
        output_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", prefix="jenefar_edge_", delete=False) as tmp:
                output_path = tmp.name
            await edge_tts.Communicate(text, voice).save(output_path)
            if Path(player).name == "mpv":
                command = [player, "--no-video", "--really-quiet", output_path]
            else:
                command = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", output_path]
            result = await asyncio.to_thread(
                subprocess.run, command, capture_output=True, check=False, timeout=90
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "edge-tts playback failed: "
                    f"{result.stderr.decode(errors='ignore').strip() or result.returncode}"
                )
        finally:
            if animation is not None:
                animation.cancel()
                try:
                    await animation
                except asyncio.CancelledError:
                    pass
            if output_path:
                try:
                    os.unlink(output_path)
                except FileNotFoundError:
                    pass

    async def _speak_espeak(self, text: str) -> None:
        """Legacy offline espeak fallback."""
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise RuntimeError("espeak/espeak-ng is not installed.")
        rate = os.getenv("JENEFAR_ESPEAK_RATE", "165")
        animation = asyncio.create_task(self._animate_speaking(text)) if self.avatar else None
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [binary, "-s", rate, text],
                capture_output=True,
                check=False,
                timeout=90,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "espeak failed: "
                    f"{result.stderr.decode(errors='ignore').strip() or result.returncode}"
                )
        finally:
            if animation is not None:
                animation.cancel()
                try:
                    await animation
                except asyncio.CancelledError:
                    pass

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
        text = enforce_hinglish(text)
        if not text:
            return
        providers = self._tts_provider_order()
        if not providers:
            raise RuntimeError(
                "No text-to-speech provider is configured. "
                "Configure OpenAI/Groq TTS, or set JENEFAR_ENABLE_NATIVE_TTS=1 "
                "for legacy local/edge playback."
            )

        last_error: Exception | None = None
        for provider in providers:
            if provider in {"edge", "espeak", "local"}:
                available = self._tts_configured(provider)
            else:
                available = self._audio_pool.available(provider)
            if not available:
                continue
            try:
                if provider == "openai":
                    await self._speak_openai(text)
                elif provider == "groq":
                    await self._speak_groq(text)
                elif provider == "edge":
                    await self._speak_edge(text)
                elif provider == "espeak":
                    await self._speak_espeak(text)
                else:
                    await self._speak_local(text)
                return
            except Exception as exc:
                last_error = exc
                # Groq Orpheus can reject the request with a model-terms error
                # even though the API key itself is valid. Treat this as a
                # provider capability failure rather than repeatedly retrying it.
                message = str(exc).lower()
                if provider == "groq" and (
                    "terms" in message
                    or "model_terms_required" in message
                ):
                    self._mark_failed_provider(
                        provider,
                        RuntimeError("groq tts model terms required"),
                    )
                    print("[JENEFAR] Groq TTS terms unavailable; moving to local voice fallback.")
                    continue
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

    def reset_audio_health(self) -> None:
        """Forget provider cooldowns after a recoverable TTS/STT failure."""
        self._audio_pool = ProviderPool()

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
