from __future__ import annotations
from dataclasses import dataclass, field
import time

@dataclass(frozen=True)
class BenchmarkCase:
    case_id:str
    prompt:str
    expected:str
    tags:tuple[str,...]=()

@dataclass
class BenchmarkResult:
    case_id:str
    passed:bool
    actual:str
    elapsed_s:float
    error:str|None=None

class BenchmarkRunner:
    def __init__(self, evaluator=None):
        self.evaluator=evaluator or (lambda actual,expected: actual.strip()==expected.strip())
    def run(self,cases:list[BenchmarkCase], handler):
        results=[]
        for case in cases:
            started=time.monotonic()
            try:
                actual=str(handler(case.prompt)); passed=bool(self.evaluator(actual,case.expected)); error=None
            except Exception as exc:
                actual=""; passed=False; error=f"{type(exc).__name__}: {exc}"
            results.append(BenchmarkResult(case.case_id,passed,actual,time.monotonic()-started,error))
        return results
    @staticmethod
    def summary(results):
        total=len(results); passed=sum(r.passed for r in results)
        return {"total":total,"passed":passed,"failed":total-passed,"success_rate":passed/total if total else 0.0,"avg_latency_s":sum(r.elapsed_s for r in results)/total if total else 0.0}
