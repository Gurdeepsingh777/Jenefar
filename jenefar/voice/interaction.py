from __future__ import annotations
import threading
from dataclasses import dataclass
@dataclass
class VoiceInteractionState:
    listening: bool=False; speaking: bool=False; interrupted: bool=False; turn_id: int=0
class VoiceInteractionController:
    """Turn-taking state for barge-in and interruptible TTS."""
    def __init__(self): self._lock=threading.RLock(); self.state=VoiceInteractionState()
    def begin_listening(self): 
        with self._lock: self.state.turn_id+=1; self.state.listening=True; self.state.speaking=False; self.state.interrupted=False; return self.state.turn_id
    def begin_speaking(self):
        with self._lock: self.state.speaking=True; self.state.listening=False; self.state.interrupted=False; return self.state.turn_id
    def interrupt(self):
        with self._lock: self.state.interrupted=True; self.state.speaking=False; self.state.listening=True
    def should_stop_speech(self, turn_id): 
        with self._lock: return turn_id!=self.state.turn_id or self.state.interrupted
    def end_turn(self):
        with self._lock: self.state.listening=False; self.state.speaking=False; self.state.interrupted=False
    def snapshot(self):
        with self._lock: return {"listening":self.state.listening,"speaking":self.state.speaking,"interrupted":self.state.interrupted,"turn_id":self.state.turn_id}
