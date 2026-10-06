from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import threading, time

@dataclass
class Histogram:
    count:int=0; total:float=0.0; maximum:float=0.0
    def observe(self,value:float): self.count+=1; self.total+=value; self.maximum=max(self.maximum,value)
    def snapshot(self): return {"count":self.count,"avg":self.total/self.count if self.count else 0.0,"max":self.maximum}

class RuntimeMetrics:
    def __init__(self):
        self._lock=threading.RLock(); self.counters=defaultdict(int); self.histograms=defaultdict(Histogram); self.cost_usd=0.0; self.tokens=0
    def inc(self,name:str,value:int=1): 
        with self._lock: self.counters[name]+=value
    def observe(self,name:str,value:float):
        with self._lock: self.histograms[name].observe(float(value))
    def record_llm(self,tokens:int=0,cost_usd:float=0.0,latency_s:float|None=None):
        with self._lock: self.tokens+=max(0,tokens); self.cost_usd+=max(0.0,cost_usd)
        if latency_s is not None: self.observe("llm_latency_seconds",latency_s)
    def snapshot(self):
        with self._lock: return {"counters":dict(self.counters),"histograms":{k:v.snapshot() for k,v in self.histograms.items()},"tokens":self.tokens,"cost_usd":round(self.cost_usd,8)}
