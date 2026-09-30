from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from jenefar.voice.provider import ProviderVoiceRuntime


class BrowserVoiceBridge:
    """Process finalized browser speech transcripts through Jenefar."""

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

    def _publish(self, state: str, text: str = "") -> None:
        if self.avatar is not None:
            self.avatar.publish(state, text)

    def handle_text(self, text: str) -> dict[str, Any]:
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
            return {"ok": True, "ignored": True, "reason": "duplicate", "text": raw}

        if normalized.strip() == "exit":
            self._last_text = normalized
            self._last_at = now
            return {"ok": True, "exit": True, "text": raw}

        matched = self.orchestrator.wakeword.matched_phrase(raw)
        strict = os.getenv("JENEFAR_REQUIRE_WAKE_WORD", "").strip().lower() in {
            "1", "true", "yes"
        }

        if self.orchestrator.state.name == "SLEEPING":
            if matched is not None:
                command = self.orchestrator.wakeword.remove_wake_phrase(raw)
            elif strict:
                return {
                    "ok": True,
                    "ignored": True,
                    "reason": "wakeword_required",
                    "text": raw,
                }
            else:
                command = raw

            if matched == "hello jenefar":
                self._conversation_language = "Hinglish"

            self._publish("listening", raw)

            if not command:
                reply = "Haan, boliye. Main sun rahi hoon."
            else:
                reply = self.orchestrator.handle(
                    command,
                    response_language=self._conversation_language,
                )
        else:
            self._publish("listening", raw)
            reply = self.orchestrator.handle(
                raw,
                response_language=self._conversation_language,
            )

        self._last_text = normalized
        self._last_at = now

        spoken = False
        tts_error = ""
        try:
            asyncio.run(self.voice.speak(reply))
            spoken = True
        except Exception as exc:
            tts_error = f"{type(exc).__name__}: {exc}"
            self.voice.reset_audio_health()
        finally:
            self._publish("idle", "")

        return {
            "ok": True,
            "text": raw,
            "reply": reply,
            "spoken": spoken,
            "tts_error": tts_error,
        }
