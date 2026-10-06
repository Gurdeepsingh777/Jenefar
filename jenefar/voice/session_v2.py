from __future__ import annotations
from dataclasses import dataclass
import threading, time

@dataclass
class VoiceTurn:
    turn_id: str
    transcript: str
    started_at: float
    ended_at: float|None=None
    interrupted: bool=False

class VoiceSession:
    def __init__(self):
        self._lock=threading.RLock(); self.active: VoiceTurn|None=None; self.history:list[VoiceTurn]=[]
    def begin(self, turn_id: str, transcript: str) -> VoiceTurn:
        with self._lock:
            if self.active: self.active.interrupted=True; self.active.ended_at=time.time(); self.history.append(self.active)
            self.active=VoiceTurn(turn_id, transcript, time.time()); return self.active
    def interrupt(self) -> VoiceTurn|None:
        with self._lock:
            if not self.active: return None
            self.active.interrupted=True; self.active.ended_at=time.time(); item=self.active; self.history.append(item); self.active=None; return item
    def finish(self) -> VoiceTurn|None:
        with self._lock:
            if not self.active: return None
            self.active.ended_at=time.time(); item=self.active; self.history.append(item); self.active=None; return item
