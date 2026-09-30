from __future__ import annotations

import asyncio
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any

from jenefar.voice.provider import ProviderVoiceRuntime
from jenefar.voice.speech import clean_for_speech


class BrowserVoiceBridge:
    """Concurrent browser voice task manager with serialized speech output."""

    def __init__(self, orchestrator, avatar=None):
        self.orchestrator = orchestrator
        self.avatar = avatar
        self.voice = ProviderVoiceRuntime(orchestrator, avatar=avatar)
        self._last_text = ""
        self._last_at = 0.0
        self._repeat_window = float(
            os.getenv("JENEFAR_BROWSER_VOICE_REPEAT_WINDOW", "1.8")
        )
        self._conversation_language = "Hinglish"
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(os.getenv("JENEFAR_VOICE_TASK_WORKERS", "3"))),
            thread_name_prefix="jenefar-task",
        )
        self._speech_queue: Queue[tuple[str, str]] = Queue()
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
        self._publish("queued", f"Queued: {raw}", task_id)
        future = self._executor.submit(self._run_task, task_id, raw)
        future.add_done_callback(lambda done: self._task_callback(task_id, done))
        return {
            "ok": True,
            "accepted": True,
            "task_id": task_id,
            "text": raw,
            "status": "queued",
        }

    def handle_text(self, text: str) -> dict[str, Any]:
        return self.submit_text(text)

    def _task_callback(self, task_id: str, future) -> None:
        try:
            future.result()
        except Exception as exc:
            self._publish(
                "error",
                f"Task {task_id} failed: {type(exc).__name__}: {exc}",
                task_id,
            )

    def _run_task(self, task_id: str, raw: str) -> None:
        self._publish("thinking", f"Processing: {raw}", task_id)

        matched = self.orchestrator.wakeword.matched_phrase(raw)
        strict = os.getenv("JENEFAR_REQUIRE_WAKE_WORD", "").strip().lower() in {
            "1", "true", "yes"
        }

        try:
            if self.orchestrator.state.name == "SLEEPING":
                if matched is not None:
                    command = self.orchestrator.wakeword.remove_wake_phrase(raw)
                elif strict:
                    self._publish(
                        "idle",
                        "Wake word required; task ignored.",
                        task_id,
                    )
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

            speech_text = clean_for_speech(reply)
            self._publish("result", reply, task_id)
            if speech_text:
                self._speech_queue.put((task_id, speech_text))
            else:
                self._publish("completed", "Task completed.", task_id)
        except Exception as exc:
            self._publish(
                "error",
                f"Task {task_id}: {type(exc).__name__}: {exc}",
                task_id,
            )
            self._speech_queue.put(
                (
                    task_id,
                    clean_for_speech(
                        "Task complete nahi ho saka. Pura error browser ke result panel me dikh raha hai."
                    ),
                )
            )

    def _speech_loop(self) -> None:
        while True:
            task_id, text = self._speech_queue.get()
            try:
                self._publish("speaking", text, task_id)
                try:
                    asyncio.run(self.voice.speak(text))
                except Exception as exc:
                    self.voice.reset_audio_health()
                    self._publish(
                        "error",
                        f"TTS failed for task {task_id}: {type(exc).__name__}: {exc}",
                        task_id,
                    )
                    self._publish("speaking_fallback", text, task_id)
            finally:
                self._speech_queue.task_done()
                if self._speech_queue.empty():
                    self._publish("idle", "Ready.", "")

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)
