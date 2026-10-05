from __future__ import annotations

import html
from pathlib import Path

from jenefar.evaluation.loop import EvaluationLoop
from jenefar.evaluation.trace import TraceStore


def render_dashboard(
    path: str | Path = "data/evaluations.jsonl",
    trace_path: str | Path = "data/execution_traces.jsonl",
) -> str:
    evaluations = EvaluationLoop(path).recent(1000)
    traces = TraceStore(trace_path)
    trace_rows = traces.recent(100)
    summary = traces.summary(1000)
    count = len(evaluations)
    passed = sum(1 for item in evaluations if item.get("passed"))
    avg = sum(float(item.get("score", 0)) for item in evaluations) / count if count else 0.0

    rows = []
    for item in reversed(evaluations[-100:]):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('task', ''))[:160])}</td>"
            f"<td>{float(item.get('score', 0)):.2f}</td>"
            f"<td>{'PASS' if item.get('passed') else 'FAIL'}</td>"
            f"<td>{html.escape(str(item.get('agent', '')))}</td>"
            f"<td>{html.escape(str(item.get('provider', '')))}</td>"
            f"<td>{html.escape(', '.join(item.get('reasons', ())))}</td>"
            "</tr>"
        )

    trace_table = []
    for item in reversed(trace_rows):
        trace_table.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('trace_id', ''))[:12])}</td>"
            f"<td>{html.escape(str(item.get('task', ''))[:100])}</td>"
            f"<td>{html.escape(str(item.get('status', '')))}</td>"
            f"<td>{html.escape(str(item.get('actual_agent', '')))}</td>"
            f"<td>{float(item.get('elapsed_ms') or 0):.0f} ms</td>"
            f"<td>{len(item.get('tool_calls', []))}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Jenefar Evaluation</title>
<style>
body{{font-family:system-ui;background:#070812;color:#eef2ff;margin:0;padding:28px}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}
.card{{padding:18px;border:1px solid #222642;border-radius:16px;background:#0d1020}}
table{{width:100%;border-collapse:collapse;margin-top:20px}}
th,td{{padding:10px;border-bottom:1px solid #222642;text-align:left;font-size:13px;vertical-align:top}}
section{{margin-top:28px}}
</style></head><body>
<h1>Jenefar Evaluation Dashboard</h1>
<div class="grid">
<div class="card"><b>Evaluations</b><div>{count}</div></div>
<div class="card"><b>Pass rate</b><div>{(passed / count * 100) if count else 0:.1f}%</div></div>
<div class="card"><b>Average score</b><div>{avg:.2f}</div></div>
<div class="card"><b>Traces</b><div>{summary["traces"]}</div></div>
<div class="card"><b>Trace success</b><div>{summary["success_rate"] * 100:.1f}%</div></div>
<div class="card"><b>Trace failure</b><div>{summary["failure_rate"] * 100:.1f}%</div></div>
</div>

<section>
<h2>Runtime health</h2>
<p>Average latency: {summary["average_elapsed_ms"]:.0f} ms · Approval traces: {summary["approval_traces"]}</p>
<p>Providers: {html.escape(", ".join(summary["providers"]) or "n/a")}</p>
<p>Agents: {html.escape(", ".join(summary["agents"]) or "n/a")}</p>
<p>Last trace: {html.escape(summary.get("last_status") or "n/a")} · Statuses: {html.escape(", ".join(f"{key}={value}" for key, value in summary.get("statuses", {}).items()) or "n/a")}</p>
</section>

<section><h2>Quality evaluations</h2>
<table><thead><tr><th>Task</th><th>Score</th><th>Status</th><th>Agent</th><th>Provider</th><th>Signals</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></section>

<section><h2>Execution traces</h2>
<table><thead><tr><th>Trace</th><th>Task</th><th>Status</th><th>Agent</th><th>Latency</th><th>Tools</th></tr></thead>
<tbody>{''.join(trace_table)}</tbody></table></section>
</body></html>"""


__all__ = ["render_dashboard"]
