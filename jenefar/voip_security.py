"""Defensive, offline VoIP parser source analyzer.

This module does not send packets, exploit devices, execute payloads, or alter logs.
It flags source-level patterns for manual review and emits remediation guidance.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    line: int
    title: str
    evidence: str
    recommendation: str


RULES = (
    (
        "VOIP001",
        "high",
        re.compile(r"\bmemcpy\s*\(\s*([^,]+),\s*([^,]+),\s*([^)]+)\)", re.I),
        "Copy operation needs a proven destination bound",
        "Verify the copied length is non-negative and no greater than the destination capacity before the copy.",
    ),
    (
        "VOIP002",
        "high",
        re.compile(r"\b(?:int|long|ssize_t)\s+\w*(?:size|len|length|count)\w*\b", re.I),
        "Signed length variable may allow invalid sizes",
        "Use size_t only after validating input, reject negative values before conversion, and check arithmetic overflow.",
    ),
    (
        "VOIP003",
        "medium",
        re.compile(r"\b(?:packet_size|packet_len|payload_len|length)\s*\*\s*\w+|\b\w+\s*\*\s*(?:packet_size|packet_len|payload_len|length)\b", re.I),
        "Length arithmetic may overflow",
        "Use checked arithmetic (for example, validate a <= SIZE_MAX / b before multiplication) and reject malformed lengths.",
    ),
    (
        "VOIP004",
        "medium",
        re.compile(r"\b(?:parse|decode|process)\w*(?:packet|frame|rtp|srtp|webrtc)\w*\s*\(", re.I),
        "Network-facing parser entry point requires review",
        "Confirm every read is bounds-checked, malformed input fails closed, and parser fuzz tests cover truncated and oversized inputs.",
    ),
)


def analyze_source(source: str) -> list[Finding]:
    """Return heuristic source-review findings; findings are not proof of exploitability."""
    findings: list[Finding] = []
    lines = source.splitlines()
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*", "#")):
            continue
        for rule_id, severity, pattern, title, recommendation in RULES:
            match = pattern.search(line)
            if not match:
                continue
            # VOIP001 is only a review signal; a nearby guard may make the copy safe.
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=severity,
                    line=index,
                    title=title,
                    evidence=stripped[:240],
                    recommendation=recommendation,
                )
            )
    return findings


def analyze_file(path: Path) -> dict[str, object]:
    source = path.read_text(encoding="utf-8", errors="replace")
    findings = analyze_source(source)
    return {
        "target": str(path),
        "mode": "offline-static-review",
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
        "limitations": [
            "Heuristic matches can be false positives and do not establish exploitability.",
            "A clean result does not prove the parser is safe.",
            "No network traffic is sent and no target device is contacted.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline heuristic review of C/C++ VoIP/WebRTC packet parser source."
    )
    parser.add_argument("source", type=Path, help="Path to a source file you are authorized to review")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)
    if not args.source.is_file():
        parser.error(f"source file not found: {args.source}")
    report = analyze_file(args.source)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"VoIP source review: {report['target']}")
        print(f"Findings: {report['finding_count']}")
        for finding in report["findings"]:
            print(f"[{finding['severity'].upper()}] {finding['rule_id']} line {finding['line']}: {finding['title']}")
            print(f"  Evidence: {finding['evidence']}")
            print(f"  Fix: {finding['recommendation']}")
        for note in report["limitations"]:
            print(f"NOTE: {note}")
    return 1 if report["finding_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
