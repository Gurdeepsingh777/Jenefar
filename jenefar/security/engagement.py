from __future__ import annotations
import json,time
from pathlib import Path
class SecurityEngagement:
    """Persistent authorized security engagement and findings ledger."""
    def __init__(self,path="data/security_engagement.json"): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
    def _load(self): return json.loads(self.path.read_text()) if self.path.exists() else {"engagement":None,"findings":[]}
    def start(self,name,scope):
        scope=[str(x).strip() for x in scope if str(x).strip()]
        if not scope: raise ValueError("An authorized scope is required.")
        payload={"name":name.strip(),"scope":scope,"started_at":time.time()}
        self.path.write_text(json.dumps({"engagement":payload,"findings":[]},indent=2)); return payload
    def add_finding(self,title,severity,target,evidence,recommendation):
        severity=severity.lower().strip()
        if severity not in {"info","low","medium","high","critical"}: raise ValueError("Invalid severity")
        data=self._load()
        if not data.get("engagement"): raise RuntimeError("Start an authorized engagement first.")
        finding={"id":f"F-{len(data['findings'])+1:04d}","title":title.strip(),"severity":severity,"target":target.strip(),"evidence":evidence[-20000:],"recommendation":recommendation.strip(),"created_at":time.time()}
        data["findings"].append(finding); self.path.write_text(json.dumps(data,indent=2)); return finding
    def report(self):
        data=self._load(); order={"critical":4,"high":3,"medium":2,"low":1,"info":0}
        return {"engagement":data.get("engagement"),"finding_count":len(data.get("findings",[])),"findings":sorted(data.get("findings",[]),key=lambda x:order.get(x.get("severity","info"),0),reverse=True)}
