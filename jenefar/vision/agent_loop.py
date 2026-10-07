from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
@dataclass
class VisionAction:
    action:dict[str,Any]; verified:bool; observation:dict[str,Any]
class VisionAgentLoop:
    """Generic bounded observe -> act -> verify loop for GUI tasks."""
    def __init__(self,vision,*,max_actions:int=8): self.vision=vision; self.max_actions=max(1,min(int(max_actions),20))
    def run(self,task,actions,*,verify:Callable[[str,dict[str,Any]],bool]|None=None):
        out=[]
        for action in actions[:self.max_actions]:
            kind=str(action.get("type") or "").lower(); query=str(action.get("query") or task)
            if kind=="click": result=self.vision.locate_and_click(query,verify=action.get("verify"))
            elif kind=="type": result=self.vision.locate_and_type(query,str(action.get("text") or ""),verify=action.get("verify"))
            elif kind=="observe": result=self.vision.analyze(query)
            else: raise ValueError(f"Unsupported vision action: {kind}")
            ok=bool(result.get("verification",{}).get("screen_changed",True))
            if verify is not None: ok=bool(verify(task,result))
            out.append(VisionAction(action,ok,result))
            if not ok: break
        return out
