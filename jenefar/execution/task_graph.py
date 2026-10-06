from __future__ import annotations
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from pathlib import Path
import json, threading, time
from jenefar.core.cancellation import CancellationToken

@dataclass
class TaskNode:
    node_id: str
    action: callable
    deps: set[str] = field(default_factory=set)
    timeout: float = 60.0
    retries: int = 0
    critical: bool = True
    rollback: callable | None = None

@dataclass
class NodeResult:
    node_id: str
    state: str
    value: object = None
    error: str | None = None
    attempts: int = 0
    elapsed: float = 0.0

class TaskGraph:
    def __init__(self, checkpoint_path: str | Path | None = None):
        self.nodes: dict[str, TaskNode] = {}
        self.results: dict[str, NodeResult] = {}
        self._lock = threading.RLock()
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
    def add(self, node: TaskNode) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"duplicate task node: {node.node_id}")
        if node.timeout <= 0 or node.retries < 0:
            raise ValueError("invalid timeout/retry configuration")
        self.nodes[node.node_id] = node
    def validate(self) -> None:
        for node in self.nodes.values():
            missing = node.deps - self.nodes.keys()
            if missing:
                raise ValueError(f"{node.node_id} depends on missing nodes: {sorted(missing)}")
        visiting, visited = set(), set()
        def visit(n: str):
            if n in visiting: raise ValueError("task graph contains a cycle")
            if n in visited: return
            visiting.add(n)
            for dep in self.nodes[n].deps: visit(dep)
            visiting.remove(n); visited.add(n)
        for n in self.nodes: visit(n)
    def _save(self):
        if not self.checkpoint_path: return
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.checkpoint_path.with_suffix(".tmp")
        data = {k: vars(v) for k,v in self.results.items()}
        tmp.write_text(json.dumps(data, default=str, sort_keys=True), encoding="utf-8")
        tmp.replace(self.checkpoint_path)
    def run(self, *, context: object = None, cancel_token: CancellationToken | None = None, max_workers: int = 4) -> dict[str, NodeResult]:
        self.validate()
        pending = set(self.nodes)
        workers = max(1, min(max_workers, len(self.nodes) or 1))
        while pending:
            if cancel_token: cancel_token.raise_if_cancelled()
            ready = [n for n in pending if self.nodes[n].deps.issubset(self.results) and all(self.results[d].state == "completed" for d in self.nodes[n].deps)]
            blocked = [n for n in pending if any(self.results.get(d, NodeResult(d,"")).state in {"failed","cancelled"} for d in self.nodes[n].deps)]
            for n in blocked:
                self.results[n] = NodeResult(n, "blocked", error="dependency failed")
                pending.remove(n)
            if not ready:
                if pending: raise RuntimeError("task graph deadlock or failed dependency")
                break
            with ThreadPoolExecutor(max_workers=min(workers, len(ready))) as pool:
                futures = {pool.submit(self._run_node, self.nodes[n], context, cancel_token): n for n in ready}
                for future in as_completed(futures):
                    n = futures[future]
                    self.results[n] = future.result()
                    pending.remove(n)
                    self._save()
            if any(r.state == "failed" and self.nodes[r.node_id].critical for r in self.results.values()):
                break
        return dict(self.results)
    def _run_node(self, node: TaskNode, context: object, token: CancellationToken | None) -> NodeResult:
        started, attempts = time.monotonic(), 0
        last_error = None
        for attempts in range(1, node.retries + 2):
            if token: token.raise_if_cancelled()
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(node.action, context)
            try:
                value = future.result(timeout=max(0.001, float(node.timeout)))
                return NodeResult(
                    node.node_id,
                    "completed",
                    value=value,
                    attempts=attempts,
                    elapsed=time.monotonic() - started,
                )
            except (FutureTimeoutError, TimeoutError) as exc:
                future.cancel()
                last_error = f"node timeout after {node.timeout:.3f}s"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            finally:
                # Do not wait for a timed-out action. The action must itself
                # honor cancellation/deadlines if it performs external work.
                executor.shutdown(wait=False, cancel_futures=True)
        return NodeResult(node.node_id, "failed", error=last_error, attempts=attempts, elapsed=time.monotonic()-started)
    def rollback(self) -> list[str]:
        rolled = []
        for node_id, result in reversed(list(self.results.items())):
            if result.state == "completed" and self.nodes[node_id].rollback:
                try: self.nodes[node_id].rollback(result.value); rolled.append(node_id)
                except Exception: pass
        return rolled
