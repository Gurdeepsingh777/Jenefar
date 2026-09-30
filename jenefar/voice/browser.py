from __future__ import annotations

import os
import threading
import time
import uuid
from queue import Queue
from typing import Any

from jenefar.voice.speech import enforce_hinglish


class BrowserVoiceBridge:
    """Concurrent browser voice task manager with serialized speech output."""

    def __init__(self, orchestrator, avatar=None):
        self.orchestrator = orchestrator
        self.avatar = avatar
        self._last_text = ""
        self._last_at = 0.0
        self._repeat_window = float(
            os.getenv("JENEFAR_BROWSER_VOICE_REPEAT_WINDOW", "1.8")
        )
        self._conversation_language = "Hinglish"
        self._task_lock = threading.Lock()
        self._speech_queue: Queue[tuple[str, str]] = Queue(maxsize=8)
        self._speech_thread = threading.Thread(
            target=self._speech_loop,
            name="jenefar-speech-queue",
            daemon=True,
        )
        self._speech_thread.start()

    def _publish(self, state: str, text: str = "", task_id: str = "") -> None:
        if self.avatar is not None:
            self.avatar.publish(state, text, task_id=task_id)

    def submit_text(self, text: str) -> dict[str, Any]:
        raw = " ".join(str(text or "").strip().split())
        if not raw:
            return {"ok": False, "ignored": True, "reason": "empty"}

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
                "text": raw,
            }

        if normalized.strip() == "exit":
            self._last_text = normalized
            self._last_at = now
            return {"ok": True, "exit": True, "text": raw}

        self._last_text = normalized
        self._last_at = now
        task_id = uuid.uuid4().hex[:10]
        self._publish("queued", "", task_id)

        if not self._task_lock.acquire(blocking=False):
            return {
                "ok": True,
                "accepted": False,
                "queued": False,
                "busy": True,
                "task_id": task_id,
                "text": raw,
                "status": "busy",
            }

        worker = threading.Thread(
            target=self._run_task_guarded,
            args=(task_id, raw),
            name=f"jenefar-task-{task_id}",
            daemon=True,
        )
        worker.start()
        return {
            "ok": True,
            "accepted": True,
            "task_id": task_id,
            "text": raw,
            "status": "running",
        }

    def handle_text(self, text: str) -> dict[str, Any]:
        return self.submit_text(text)

    def _run_task_guarded(self, task_id: str, raw: str) -> None:
        try:
            self._run_task(task_id, raw)
        finally:
            self._task_lock.release()

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
                        response_language=self._conversation_language,
                    )
                )
            else:
                reply = self.orchestrator.handle(
                    raw,
                    response_language=self._conversation_language,
                )

            speech_text = enforce_hinglish(reply)
            self._publish("result", "", task_id)
            if speech_text:
                self._speech_queue.put((task_id, speech_text))
            else:
                self._publish("completed", "", task_id)
        except Exception:
            self._publish("error", "Task complete nahi ho saka.", task_id)
            self._speech_queue.put(
                (
                    task_id,
                    enforce_hinglish(
                        "Task complete nahi ho saka. Pura error browser ke result panel me dikh raha hai."
                    ),
                )
            )

    def _speech_loop(self) -> None:
        # Browser owns actual audio playback. This worker only publishes the
        # response event so app.js can use speechSynthesis without Python audio.
        while True:
            task_id, text = self._speech_queue.get()
            try:
                self._publish("speaking", text, task_id)
                self._publish("speaking_fallback", text, task_id)
                self._publish("completed", "", task_id)
            finally:
                self._speech_queue.task_done()
                if self._speech_queue.empty():
                    self._publish("idle", "", "")

    def shutdown(self) -> None:
        if self._task_lock.locked():
            try:
                self._task_lock.release()
            except RuntimeError:
                pass
