from __future__ import annotations

import queue
import threading
import time
from dataclasses import asdict, dataclass

from jenefar.avatar.expression import ExpressionEngine
from jenefar.avatar.viseme import text_to_visemes


@dataclass(frozen=True)
class AvatarEvent:
    state: str
    text: str = ""
    level: float = 0.0
    task_id: str = ""
    emotion: str = "neutral"
    intensity: float = 0.0
    timestamp: float = 0.0
    audio_b64: str = ""
    audio_mime: str = ""
    visemes: tuple[dict[str, object], ...] = ()

    def payload(self) -> dict[str, object]:
        value = asdict(self)
        value["timestamp"] = self.timestamp or time.time()
        return value


class AvatarController:
    """Thread-safe state bridge between Jenefar runtime and the avatar UI."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: set[queue.Queue[dict[str, object]]] = set()
        self._expressions = ExpressionEngine()
        self._current = AvatarEvent("idle").payload()

    def publish(
        self,
        state: str,
        text: str = "",
        level: float = 0.0,
        *,
        task_id: str = "",
        audio_b64: str = "",
        audio_mime: str = "",
    ) -> None:
        bounded_level = max(0.0, min(1.0, float(level)))
        expression = self._expressions.classify(state, text)
        event = AvatarEvent(
            state=state,
            text=text,
            level=bounded_level,
            task_id=task_id,
            emotion=expression.name,
            intensity=expression.intensity,
            timestamp=time.time(),
            audio_b64=str(audio_b64 or ""),
            audio_mime=str(audio_mime or ""),
            visemes=tuple(item.__dict__ for item in text_to_visemes(text)) if text else (),

        ).payload()
        with self._lock:
            self._current = event
            dead: list[queue.Queue[dict[str, object]]] = []
            for subscriber in self._subscribers:
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    try:
                        subscriber.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        subscriber.put_nowait(event)
                    except queue.Full:
                        dead.append(subscriber)
            for subscriber in dead:
                self._subscribers.discard(subscriber)

    def current(self) -> dict[str, object]:
        with self._lock:
            return dict(self._current)

    def subscribe(self, maxsize: int = 32) -> queue.Queue[dict[str, object]]:
        subscriber: queue.Queue[dict[str, object]] = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.add(subscriber)
            try:
                subscriber.put_nowait(dict(self._current))
            except queue.Full:
                pass
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, object]]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)
