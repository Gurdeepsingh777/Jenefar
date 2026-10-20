from __future__ import annotations

import asyncio
import array
import base64
import math
import os
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any

from jenefar.voice.speech import devanagari_to_roman, enforce_hinglish, roman_hinglish_for_voice


class BrowserVoiceBridge:
    """Browser-first voice task manager with natural browser-played TTS audio."""

    def __init__(self, orchestrator, avatar=None):
        self.orchestrator = orchestrator
        self.avatar = avatar
        # Reuse the STT runtime so exhausted-provider cooldowns survive across
        # microphone utterances instead of retrying a dead API on every recording.
        from jenefar.voice.provider import ProviderVoiceRuntime
        self._stt_runtime = ProviderVoiceRuntime(orchestrator)
        self._last_text = ""
        self._last_at = 0.0
        self._repeat_window = float(
            os.getenv("JENEFAR_BROWSER_VOICE_REPEAT_WINDOW", "1.8")
        )
        self._conversation_language = "Hinglish"
        self._task_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="jenefar-task",
        )
        self._task_lock = threading.RLock()
        self._active_task = None
        self._task_generation = 0
        self._last_assistant_text = ""
        self._last_assistant_spoken_at = 0.0
        try:
            self._ip_echo_window = max(
                0.0,
                float(os.getenv("JENEFAR_BROWSER_IP_ECHO_WINDOW", "24")),
            )
        except (TypeError, ValueError):
            self._ip_echo_window = 24.0
        self._speech_queue: Queue[tuple[str, str]] = Queue(maxsize=8)
        self._approval_voice_lock = threading.Lock()
        self._approval_voice_results: dict[str, str] = {}
        self._tts_lock = threading.Lock()
        self._openai_tts_disabled = False
        self._gemini_tts_disabled = False
        self._piper_tts_disabled = False
        self._speech_thread = threading.Thread(
            target=self._speech_loop,
            name="jenefar-speech-queue",
            daemon=True,
        )
        self._speech_thread.start()

    def _publish(
        self,
        state: str,
        text: str = "",
        task_id: str = "",
        *,
        audio_b64: str = "",
        audio_mime: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        if self.avatar is not None:
            self.avatar.publish(
                state,
                text,
                task_id=task_id,
                audio_b64=audio_b64,
                audio_mime=audio_mime,
                data=data,
            )

    @staticmethod
    def _display_text(text: str) -> str:
        # Preserve markdown/code/technical tokens; only force Hindi script to Roman.
        return devanagari_to_roman(str(text or "").strip())

    def _ensure_task_lock(self):
        """Provide a lock for normal instances and lightweight embedded/test fixtures."""
        lock = getattr(self, "_task_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._task_lock = lock
        return lock

    @staticmethod
    def _require_user_reply(reply: Any) -> str:
        """Never report an empty assistant result as a successful completed task."""
        value = str(reply or "").strip()
        if not value:
            raise RuntimeError(
                "The task handler returned an empty response. Check the task trace and model diagnostics."
            )
        return value

    @staticmethod
    def _direct_openai_key() -> str:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return "" if not key or key.startswith("sk-or-") else key

    @staticmethod
    def _direct_gemini_tts_key() -> str:
        direct = os.getenv("GEMINI_API_KEY", "").strip()
        if direct:
            return direct
        base_url = (
            os.getenv("LLM_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
        ).lower()
        if "generativelanguage.googleapis.com" not in base_url:
            return ""
        return os.getenv("LLM_API_KEY", "").strip() or os.getenv("API_KEY", "").strip()

    @staticmethod
    def _gemini_tts_style(text: str) -> str:
        """Choose expressive delivery metadata without altering the spoken words."""
        configured = os.getenv("JENEFAR_GEMINI_TTS_STYLE", "").strip()
        if configured:
            return configured[:500]
        lowered = str(text or "").casefold()
        empathetic = (
            "sorry", "maaf", "takleef", "pareshan", "i understand",
            "don't worry", "chinta mat", "error", "problem", "issue",
        )
        excited = (
            "congratulations", "mubarak", "great news", "bahut achha",
            "amazing", "wonderful", "shabash", "ho gaya",
        )
        serious = ("warning", "danger", "important", "security risk", "unsafe", "critical")
        if any(marker in lowered for marker in empathetic):
            return (
                "Warm, gentle, empathetic adult female conversational voice. "
                "Speak a little more slowly, with reassuring softness, human pauses, "
                "subtle pitch variation, and caring emphasis. Natural Indian Hinglish pronunciation."
            )
        if any(marker in lowered for marker in serious):
            return (
                "Calm, serious, clear and grounded conversational delivery. "
                "Use measured pacing, natural pauses and firm but not harsh emphasis. "
                "Natural Indian Hinglish pronunciation."
            )
        if any(marker in lowered for marker in excited):
            return (
                "Warm, genuinely happy and encouraging adult female conversational voice. "
                "Sound smiling and lively, with brighter intonation, varied pitch and natural rhythm; "
                "avoid exaggerated acting. Natural Indian Hinglish pronunciation."
            )
        if "?" in lowered or any(marker in lowered for marker in ("kya ", "kaise ", "kyun ", "why ", "how ")):
            return (
                "Friendly, attentive adult female conversational voice. "
                "Sound curious and engaged with a gentle rise on questions, varied pitch, "
                "clear words and relaxed natural pauses. Natural Indian Hinglish pronunciation."
            )
        return (
            "Warm, natural, emotionally expressive adult female conversational voice for Jenefar. "
            "Use relaxed Indian Hinglish pronunciation, varied pitch and cadence, small human pauses, "
            "soft emphasis on meaningful words, and a friendly confident tone. "
            "Do not sound like a news reader, audiobook narrator or robot; avoid overacting."
        )

    def _synthesize_gemini_audio(self, text: str) -> tuple[str, str]:
        """Expressive Google Gemini TTS fallback, independent of chat-model quota."""
        key = self._direct_gemini_tts_key()
        if not key or getattr(self, "_gemini_tts_disabled", False):
            return "", ""
        import httpx

        model = os.getenv("JENEFAR_GEMINI_TTS_MODEL", "gemini-3.8-flash-tts").strip()
        voice = os.getenv("JENEFAR_GEMINI_TTS_VOICE", "Aoede").strip() or "Aoede"
        payload = {
            "model": model,
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": str(text or "")[:4096],
                    "annotations": [{
                        "type": "speech_metadata",
                        "style": self._gemini_tts_style(text),
                    }],
                }],
            }],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]},
        }
        try:
            response = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
                timeout=httpx.Timeout(45.0, connect=5.0),
            )
            response.raise_for_status()
            result = response.json()
            audio_data = (result.get("output_audio") or {}).get("data")
            mime = (result.get("output_audio") or {}).get("mime_type") or "audio/wav"
            if not audio_data:
                # REST responses expose audio blocks inside steps; SDK convenience
                # objects instead expose output_audio directly.
                for step in result.get("steps", []):
                    if not isinstance(step, dict) or step.get("type") != "model_output":
                        continue
                    for block in step.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "audio" and block.get("data"):
                            audio_data = block["data"]
                            mime = block.get("mime_type") or "audio/wav"
                            break
                    if audio_data:
                        break
            if not audio_data:
                raise RuntimeError("Gemini TTS response contained no audio data.")
            # The upstream API already returns base64 audio, matching the avatar
            # event contract used for OpenAI and Edge generated audio.
            print(f"[JENEFAR] Browser TTS: expressive Gemini {model} / {voice}.")
            return str(audio_data), str(mime)
        except Exception as exc:
            error_text = str(exc).casefold()
            if any(marker in error_text for marker in (
                "429", "resource_exhausted", "rate limit", "too many requests",
                "quota", "no credits remaining", "insufficient_quota",
            )):
                self._gemini_tts_disabled = True
                print(
                    "[JENEFAR] Gemini TTS quota/rate limit reached; "
                    "skipping further Gemini TTS attempts this run."
                )
            print(
                "[JENEFAR] Expressive Gemini TTS unavailable; "
                f"trying the next voice fallback: {type(exc).__name__}: {exc}"
            )
            return "", ""

    def _synthesize_local_piper_audio(self, text: str) -> tuple[str, str]:
        """Generate browser-playable WAV audio with an explicitly configured local Piper model."""
        if getattr(self, "_piper_tts_disabled", False):
            return "", ""

        import shutil
        import subprocess
        from pathlib import Path

        executable = shutil.which("piper")
        model_value = os.getenv("JENEFAR_LOCAL_TTS_MODEL", "").strip()
        # Piper is optional. Do not log a warning on every answer when it has
        # not been configured; Edge/browser speech remain valid fallbacks.
        if not executable or not model_value:
            return "", ""

        model_path = Path(model_value).expanduser()
        if not model_path.is_file():
            self._piper_tts_disabled = True
            print(
                "[JENEFAR] Local Piper TTS skipped: JENEFAR_LOCAL_TTS_MODEL "
                f"does not point to an ONNX model file: {model_path}"
            )
            return "", ""

        clean = str(text or "").strip()
        if not clean:
            return "", ""
        try:
            timeout = max(5.0, min(90.0, float(
                os.getenv("JENEFAR_LOCAL_TTS_TIMEOUT_SECONDS", "35")
            )))
        except (TypeError, ValueError):
            timeout = 35.0

        output_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".wav", prefix="jenefar_piper_", delete=False
            ) as tmp:
                output_path = tmp.name
            result = subprocess.run(
                [
                    executable,
                    "--model", str(model_path),
                    "--output_file", output_path,
                ],
                input=clean[:4096].encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or b"").decode(
                    "utf-8", errors="replace"
                ).strip()[-500:]
                self._piper_tts_disabled = True
                print(
                    "[JENEFAR] Local Piper TTS failed; skipping further Piper attempts this run: "
                    + (detail or f"exit code {result.returncode}")
                )
                return "", ""

            with open(output_path, "rb") as handle:
                audio_data = handle.read()
            if not audio_data:
                self._piper_tts_disabled = True
                print("[JENEFAR] Local Piper TTS returned an empty WAV file; disabling it for this run.")
                return "", ""
            print(f"[JENEFAR] Browser TTS: local Piper ({model_path.name}).")
            return base64.b64encode(audio_data).decode("ascii"), "audio/wav"
        except subprocess.TimeoutExpired:
            self._piper_tts_disabled = True
            print(
                f"[JENEFAR] Local Piper TTS timed out after {timeout:g}s; "
                "skipping further Piper attempts this run."
            )
            return "", ""
        except Exception as exc:
            self._piper_tts_disabled = True
            print(
                "[JENEFAR] Local Piper TTS unavailable; "
                f"trying another voice fallback: {type(exc).__name__}: {exc}"
            )
            return "", ""
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

    def _synthesize_edge_audio(self, text: str) -> tuple[str, str]:
        try:
            import edge_tts
            voice = os.getenv("JENEFAR_EDGE_TTS_VOICE", "en-IN-NeerjaNeural")
            rate = os.getenv("JENEFAR_EDGE_TTS_RATE", "-2%")
            pitch = os.getenv("JENEFAR_EDGE_TTS_PITCH", "+2Hz")
            communicate = edge_tts.Communicate(text[:4096], voice, rate=rate, pitch=pitch)
            with tempfile.NamedTemporaryFile(suffix=".mp3", prefix="jenefar_edge_", delete=False) as tmp:
                output_path = tmp.name
            try:
                asyncio.run(communicate.save(output_path))
                with open(output_path, "rb") as handle:
                    audio_data = handle.read()
                if not audio_data:
                    raise RuntimeError("Edge TTS returned an empty audio file.")
                encoded = base64.b64encode(audio_data).decode("ascii")
                print(
                    "[JENEFAR] Browser TTS: Edge "
                    + str(voice)
                    + "."
                )
                return encoded, "audio/mpeg"
            finally:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
        except Exception as exc:
            print(
                "[JENEFAR] Edge browser TTS fallback failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return "", ""

    def _synthesize_browser_audio(self, text: str) -> tuple[str, str]:
        key = self._direct_openai_key()
        if not key or self._openai_tts_disabled:
            # Prefer expressive cloud TTS when configured, then a genuinely local
            # Piper voice before Edge (which needs internet) or browser synthesis.
            audio = self._synthesize_gemini_audio(text)
            if audio[0]:
                return audio
            audio = self._synthesize_local_piper_audio(text)
            return audio if audio[0] else self._synthesize_edge_audio(text)

        model = os.getenv("JENEFAR_BROWSER_TTS_MODEL", "gpt-4o-mini-tts").strip()
        voice = os.getenv("JENEFAR_BROWSER_TTS_VOICE", "coral").strip() or "coral"
        instructions = os.getenv(
            "JENEFAR_BROWSER_TTS_INSTRUCTIONS",
            (
                "Speak as a warm, natural, emotionally expressive adult female voice. "
                "Use a relaxed Indian conversational style for Roman Hinglish. "
                "Sound like a real person talking naturally, not a narrator or robot. "
                "Use gentle pauses, natural emphasis, and a friendly confident tone. "
                "Do not spell out Romanized Hindi words."
            ),
        )
        try:
            from openai import OpenAI

            with self._tts_lock:
                response = OpenAI(api_key=key).audio.speech.create(
                    model=model,
                    voice=voice,
                    input=text[:4096],
                    instructions=instructions,
                    response_format="wav",
                    speed=float(os.getenv("JENEFAR_BROWSER_TTS_SPEED", "0.98")),
                )
            return (
                base64.b64encode(response.content).decode("ascii"),
                "audio/wav",
            )
        except Exception as exc:
            error_text = str(exc).lower()
            if any(marker in error_text for marker in ("insufficient_quota", "credit_balance_exhausted", "no credits remaining")):
                self._openai_tts_disabled = True
                print("[JENEFAR] OpenAI TTS quota exhausted; skipping further OpenAI TTS attempts this run.")
            print(
                "[JENEFAR] Browser TTS generation failed; "
                f"trying expressive Gemini TTS: {type(exc).__name__}: {exc}"
            )
            audio = self._synthesize_gemini_audio(text)
            if audio[0]:
                return audio
            audio = self._synthesize_local_piper_audio(text)
            return audio if audio[0] else self._synthesize_edge_audio(text)

    def submit_text(self, text: str) -> dict[str, Any]:
        raw = " ".join(str(text or "").strip().split())
        if not raw:
            return {"ok": False, "ignored": True, "reason": "empty"}

        display_text = self._display_text(raw)
        normalized = self.orchestrator.wakeword.normalize_stt_text(raw)
        now = time.monotonic()
        with self._ensure_task_lock():
            if (
                normalized
                and normalized == self._last_text
                and now - self._last_at < self._repeat_window
            ):
                return {
                    "ok": True,
                    "ignored": True,
                    "reason": "duplicate",
                    "text": display_text,
                    "display_text": display_text,
                }

            if normalized.strip() == "exit":
                self._last_text = normalized
                self._last_at = now
                return {
                    "ok": True,
                    "exit": True,
                    "text": display_text,
                    "display_text": display_text,
                }

            task_id = uuid.uuid4().hex[:10]

            # Admission is atomic. A busy command must not publish a fake queued
            # task or leave a phantom RUNNING entry in the dashboard. The lock
            # also prevents two simultaneous requests from both passing the gate.
            # Do not mark a rejected busy command as the last accepted utterance:
            # the user must be able to retry the same command as soon as the active
            # task finishes, without the duplicate-speech guard swallowing it.
            if self._active_task is not None and not self._active_task.done():
                return {
                    "ok": True,
                    "accepted": False,
                    "queued": False,
                    "busy": True,
                    "task_id": task_id,
                    "text": display_text,
                    "display_text": display_text,
                    "status": "busy",
                    "reason": "assistant_busy",
                }

            self._last_text = normalized
            self._last_at = now
            self._task_generation = int(getattr(self, "_task_generation", 0)) + 1
            self._publish("listening", "You: " + display_text, task_id)
            self._publish("queued", "", task_id)
            self._active_task = self._task_executor.submit(
                self._run_task,
                task_id,
                display_text,
            )

        return {
            "ok": True,
            "accepted": True,
            "task_id": task_id,
            "text": display_text,
            "display_text": display_text,
            "status": "running",
        }

    def approve_pending(self, pending_id: str) -> dict[str, Any]:
        """Approve once, with the active voice task as the only speech owner."""
        approval_id = str(pending_id or "").strip()
        if not approval_id:
            return {"status": "error", "error": "approval id required"}

        # A spoken "yes" may already be processing on the single voice worker
        # while the user also clicks the dashboard approval button. In that case,
        # let the voice task complete the approval and speak its own result.
        active_task = self._active_task
        confirmation_parser = getattr(self.orchestrator, "_confirmation_choice", None)
        if (
            active_task is not None
            and not active_task.done()
            and callable(confirmation_parser)
            and confirmation_parser(self._last_text) is not None
        ):
            return {
                "status": "ok",
                "result": "Approval is already being processed from your voice confirmation.",
                "speech_owner": "voice_confirmation",
            }

        # Duplicate HTTP approval requests must neither execute the action nor
        # enqueue a second audio event after the first approval has completed.
        with self._approval_voice_lock:
            if approval_id in self._approval_voice_results:
                cached = {
                    "status": "ok",
                    "result": self._approval_voice_results[approval_id],
                    "duplicate": True,
                }
                cached_scan = getattr(self.orchestrator, "_latest_scan_result", None)
                if isinstance(cached_scan, dict) and cached_scan.get("kind") in {
                    "host_discovery", "port_scan"
                }:
                    cached["structured_scan"] = True
                return cached

            # Reset only after the duplicate guard, so a repeated click can still
            # reuse its cached scan result. A fresh approval must not inherit data
            # from an unrelated earlier scan.
            if hasattr(self.orchestrator, "_latest_scan_result"):
                self.orchestrator._latest_scan_result = None
            result = self.orchestrator._approve_pending(approval_id)
            task_id = uuid.uuid4().hex[:10]
            structured_scan = getattr(self.orchestrator, "_latest_scan_result", None)
            if isinstance(structured_scan, dict) and structured_scan.get("kind") in {
                "host_discovery", "port_scan"
            }:
                display = self._display_text(str(structured_scan.get("summary") or result))
                # Network results are visual-only by design: display actionable
                # rows in the glass panel instead of speaking a list of IPs/ports.
                self._publish("scan_results", display, task_id, data=structured_scan)
                self._approval_voice_results[approval_id] = display
                while len(self._approval_voice_results) > 128:
                    oldest_id = next(iter(self._approval_voice_results))
                    self._approval_voice_results.pop(oldest_id, None)
                return {"status": "ok", "result": display, "structured_scan": True}

            display = self._display_text(result)
            self._publish("result", display, task_id)
            try:
                self._speech_queue.put_nowait((task_id, display))
            except Exception:
                # If the speech queue is full, preserve visual feedback and let the
                # browser's speech fallback read the result instead.
                self._publish("speaking_fallback", display, task_id)

            self._approval_voice_results[approval_id] = display
            while len(self._approval_voice_results) > 128:
                oldest_id = next(iter(self._approval_voice_results))
                self._approval_voice_results.pop(oldest_id, None)
            return {"status": "ok", "result": display}

    def handle_text(self, text: str) -> dict[str, Any]:
        return self.submit_text(text)

    def handle_audio(self, audio: bytes, content_type: str = "audio/webm") -> dict[str, Any]:
        """Transcribe a browser MediaRecorder blob, then enqueue it as normal user text."""
        if not audio:
            print("[JENEFAR] Browser microphone upload was empty.")
            return {"ok": False, "error": "No microphone audio was received."}
        print(
            f"[JENEFAR] Browser microphone upload received: {len(audio)} bytes "
            f"({content_type or 'audio/unknown'})."
        )
        if len(audio) > 12 * 1024 * 1024:
            return {"ok": False, "error": "Audio recording is too large (limit: 12 MiB)."}
        if content_type and not str(content_type).lower().startswith("audio/"):
            return {"ok": False, "error": "Expected an audio recording from the browser microphone."}

        # Do not transcribe stale audio while an assistant reply is being
        # generated. STT may finish after that reply and otherwise enqueue
        # microphone echo as a brand-new command.
        with self._ensure_task_lock():
            active_task = getattr(self, "_active_task", None)
            task_generation_at_start = int(getattr(self, "_task_generation", 0))
            if active_task is not None and not active_task.done():
                return {
                    "ok": True,
                    "accepted": False,
                    "busy": True,
                    "status": "busy",
                    "reason": "assistant_busy",
                }
        import shutil
        import subprocess

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {
                "ok": False,
                "error": "Browser mic fallback needs ffmpeg. Install it with: sudo apt install ffmpeg",
            }
        try:
            converted = subprocess.run(
                [
                    ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le",
                    "-ac", "1", "-ar", "16000", "pipe:1",
                ],
                input=audio,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Audio conversion timed out; please try a shorter utterance."}
        except Exception as exc:
            return {"ok": False, "error": f"Audio conversion failed: {type(exc).__name__}: {exc}"}

        if converted.returncode != 0 or len(converted.stdout) < 3200:
            detail = converted.stderr.decode("utf-8", errors="replace").strip()[-400:]
            return {
                "ok": False,
                "error": "Could not decode microphone audio." + (f" {detail}" if detail else ""),
            }
        # Log only signal statistics (never the user's words) so a silent or
        # misrouted OS input device can be distinguished from an STT/model error.
        samples = array.array("h")
        samples.frombytes(converted.stdout)
        if sys.byteorder != "little":
            samples.byteswap()
        peak = max((abs(int(sample)) for sample in samples), default=0)
        rms = math.sqrt(
            sum(int(sample) * int(sample) for sample in samples) / max(1, len(samples))
        )
        print(
            "[JENEFAR] Browser microphone PCM: "
            f"samples={len(samples)} peak={peak}/32768 rms={rms:.1f}/32768."
        )
        if peak < 80 and rms < 20:
            print(
                "[JENEFAR] Microphone signal is near silence. "
                "Check System Settings → Sound → Input and select the physical microphone."
            )
        try:
            transcript = asyncio.run(
                self._stt_runtime.transcribe_pcm(converted.stdout)
            )
        except Exception as exc:
            print(
                "[JENEFAR] Browser microphone STT failed after local/cloud fallback: "
                f"{type(exc).__name__}: {exc}"
            )
            return {"ok": False, "error": f"Speech-to-text unavailable: {type(exc).__name__}: {exc}"}

        transcript = " ".join(str(transcript or "").split()).strip()
        if not transcript:
            print("[JENEFAR] Speech recognition returned an empty transcript.")
            return {"ok": True, "ignored": True, "reason": "empty_transcript"}
        print(
            f"[JENEFAR] Browser microphone command transcribed successfully "
            f"({len(transcript)} characters); submitting it to the command handler."
        )
        with self._ensure_task_lock():
            generation_changed = int(getattr(self, "_task_generation", 0)) != task_generation_at_start
        if generation_changed:
            return {
                "ok": True,
                "accepted": False,
                "busy": True,
                "status": "busy",
                "reason": "task_started_during_transcription",
                "transcript": self._display_text(transcript),
            }
        if self._is_recent_assistant_ip_echo(transcript):
            display = self._display_text(transcript)
            return {
                "ok": True,
                "ignored": True,
                "reason": "assistant_ip_echo",
                "text": display,
                "display_text": display,
                "transcript": display,
            }
        result = self.submit_text(transcript)
        result["transcript"] = self._display_text(transcript)
        return result


    def _is_recent_assistant_ip_echo(self, transcript: str) -> bool:
        """Drop a mic transcript that repeats an IP query just after an IP report."""
        if not self._last_assistant_spoken_at:
            return False
        if time.monotonic() - self._last_assistant_spoken_at > self._ip_echo_window:
            return False
        previous = self._last_assistant_text.casefold()
        if not any(marker in previous for marker in ("ip information", "local ipv4", "public ipv4")):
            return False
        matcher = getattr(self.orchestrator, "_is_ip_info_query", None)
        return bool(callable(matcher) and matcher(transcript))

    def _run_task(self, task_id: str, raw: str) -> None:
        self._publish("thinking", "", task_id)

        matched = self.orchestrator.wakeword.matched_phrase(raw)
        strict = os.getenv("JENEFAR_REQUIRE_WAKE_WORD", "").strip().lower() in {
            "1", "true", "yes"
        }
        production = getattr(self.orchestrator, "production", None)
        voice_session = getattr(production, "voice", None)
        if voice_session is not None:
            voice_session.begin(task_id, raw)

        try:
            if self.orchestrator.state.name == "SLEEPING":
                if matched is not None:
                    command = self.orchestrator.wakeword.remove_wake_phrase(raw)
                elif strict:
                    self._publish("idle", "", task_id)
                    return
                else:
                    command = raw

                if matched == "hello jenefar":
                    self._conversation_language = "Hinglish"

                reply = (
                    "Haan, boliye. Main sun rahi hoon."
                    if not command
                    else self.orchestrator.handle(
                        command,
                        response_language="Hinglish",
                    )
                )
            else:
                reply = self.orchestrator.handle(
                    raw,
                    response_language="Hinglish",
                )

            reply = self._require_user_reply(reply)
            structured_scan = getattr(self.orchestrator, "_latest_scan_result", None)
            if isinstance(structured_scan, dict) and structured_scan.get("kind") in {
                "host_discovery", "port_scan"
            }:
                display_summary = self._display_text(
                    str(structured_scan.get("summary") or reply)
                )
                # Do not synthesize or enqueue spoken IP/port lists. The browser's
                # dedicated glass results window is the sole presentation path.
                self._last_assistant_text = ""
                self._last_assistant_spoken_at = 0.0
                self._publish(
                    "scan_results",
                    display_summary,
                    task_id,
                    data=structured_scan,
                )
                return

            speech_source = enforce_hinglish(reply)
            display_reply = self._display_text(reply)
            speech_text = roman_hinglish_for_voice(speech_source)
            self._publish("result", display_reply, task_id)
            if speech_text:
                audio_b64, audio_mime = self._synthesize_browser_audio(speech_text)
                self._last_assistant_text = display_reply
                self._last_assistant_spoken_at = time.monotonic()
                self._publish(
                    "speaking",
                    display_reply,
                    task_id,
                    audio_b64=audio_b64,
                    audio_mime=audio_mime,
                )
                if not audio_b64:
                    print(
                        "[JENEFAR] No generated TTS audio is available; "
                        "requesting browser-native SpeechSynthesis fallback. "
                        "If there is no sound, check the OS Sound Output device "
                        "(do not leave 'Dummy Output' selected)."
                    )
                    self._publish("speaking_fallback", display_reply, task_id)
            else:
                self._publish("completed", "", task_id)
        except Exception as exc:
            error_text = self._display_text(
                f"Task complete nahi ho saka. Error: {type(exc).__name__}: {exc}"
            )
            self._publish("error", error_text, task_id)
            speech_text = roman_hinglish_for_voice(error_text)
            audio_b64, audio_mime = self._synthesize_browser_audio(speech_text)
            self._publish(
                "speaking",
                error_text,
                task_id,
                audio_b64=audio_b64,
                audio_mime=audio_mime,
            )
            if not audio_b64:
                print(
                    "[JENEFAR] Error speech has no generated audio; "
                    "requesting browser-native SpeechSynthesis fallback."
                )
                self._publish("speaking_fallback", error_text, task_id)
        finally:
            if voice_session is not None:
                voice_session.finish()

    def _speech_loop(self) -> None:
        # This worker only generates browser-playable audio and publishes it.
        # It never opens a local speaker device.
        while True:
            task_id, text = self._speech_queue.get()
            try:
                display_text = self._display_text(text)
                speech_text = roman_hinglish_for_voice(display_text)
                audio_b64, audio_mime = self._synthesize_browser_audio(speech_text)
                if audio_b64:
                    self._publish(
                        "speaking",
                        display_text,
                        task_id,
                        audio_b64=audio_b64,
                        audio_mime=audio_mime,
                    )
                else:
                    # Keep all speech on the avatar event path. The browser's
                    # native voice is used only if generated audio is unavailable.
                    self._publish("speaking_fallback", display_text, task_id)
            finally:
                # Queue completion means synthesis ended, not that browser
                # playback ended. Do not publish idle and unlock the mic early.
                self._speech_queue.task_done()

    def shutdown(self) -> None:
        self._task_executor.shutdown(wait=False, cancel_futures=True)
