from __future__ import annotations

import base64
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any

from jenefar.voice.speech import enforce_hinglish, roman_hinglish_for_voice


class BrowserVoiceBridge:
    """Browser-first voice task manager with natural browser-played TTS audio."""

    def __init__(self, orchestrator, avatar=None):
        self.orchestrator = orchestrator
        self.avatar = avatar
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
        self._active_task = None
        self._speech_queue: Queue[tuple[str, str]] = Queue(maxsize=8)
        self._tts_lock = threading.Lock()
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
    ) -> None:
        if self.avatar is not None:
            self.avatar.publish(
                state,
                text,
                task_id=task_id,
                audio_b64=audio_b64,
                audio_mime=audio_mime,
            )

    @staticmethod
    def _display_text(text: str) -> str:
        return enforce_hinglish(str(text or "").strip(), max_chars=12000)

    @staticmethod
    def _direct_openai_key() -> str:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return "" if not key or key.startswith("sk-or-") else key

    def _synthesize_browser_audio(self, text: str) -> tuple[str, str]:
        key = self._direct_openai_key()
        if not key:
            return "", ""

        model = os.getenv("JENEFAR_BROWSER_TTS_MODEL", "gpt-4o-mini-tts").strip()
        voice = os.getenv("JENEFAR_BROWSER_TTS_VOICE", "coral").strip() or "coral"
        instructions = os.getenv(
            "JENEFAR_BROWSER_TTS_INSTRUCTIONS",
            (
                "Speak as a warm, natural, emotionally expressive adult female voice. "
                "Use a relaxed Indian conversational style for Roman Hinglish. "
                "Sound like a real person talking naturally, not like a narrator or robot. "
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
            print(
                "[JENEFAR] Browser TTS generation failed; "
                f"falling back to Web SpeechSynthesis: {type(exc).__name__}: {exc}"
            )
            return "", ""

    def submit_text(self, text: str) -> dict[str, Any]:
        raw = " ".join(str(text or "").strip().split())
        if not raw:
            return {"ok": False, "ignored": True, "reason": "empty"}

        display_text = self._display_text(raw)
        normalized = self.orchestrator.wakeword.normalize_stt_text(raw)
        now = time.monotonic()
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

        self._last_text = normalized
        self._last_at = now
        task_id = uuid.uuid4().hex[:10]
        self._publish("listening", "You: " + display_text, task_id)
        self._publish("queued", "", task_id)

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
            }

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

    def handle_text(self, text: str) -> dict[str, Any]:
        return self.submit_text(text)

    def _run_task(self, task_id: str, raw: str) -> None:
        self._publish("thinking", "", task_id)

        matched = self.orchestrator.wakeword.matched_phrase(raw)
        strict = os.getenv("JENEFAR_REQUIRE_WAKE_WORD", "").strip().lower() in {
            "1", "true", "yes"
        }

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

            display_reply = self._display_text(reply)
            speech_text = roman_hinglish_for_voice(display_reply)
            self._publish("result", display_reply, task_id)
            if speech_text:
                audio_b64, audio_mime = self._synthesize_browser_audio(speech_text)
                self._publish(
                    "speaking",
                    display_reply,
                    task_id,
                    audio_b64=audio_b64,
                    audio_mime=audio_mime,
                )
                if not audio_b64:
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
                self._publish("speaking_fallback", error_text, task_id)

    def _speech_loop(self) -> None:
        # This worker only generates browser-playable audio and publishes it.
        # It never opens a local speaker device.
        while True:
            task_id, text = self._speech_queue.get()
            try:
                display_text = self._display_text(text)
                speech_text = roman_hinglish_for_voice(display_text)
                audio_b64, audio_mime = self._synthesize_browser_audio(speech_text)
                self._publish(
                    "speaking",
                    display_text,
                    task_id,
                    audio_b64=audio_b64,
                    audio_mime=audio_mime,
                )
            finally:
                self._speech_queue.task_done()
                if self._speech_queue.empty():
                    self._publish("idle", "", "")

    def shutdown(self) -> None:
        self._task_executor.shutdown(wait=False, cancel_futures=True)
