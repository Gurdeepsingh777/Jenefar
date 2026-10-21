# Defensive VoIP / WebRTC Parser Review

Jenefar includes an **offline heuristic source analyzer** for authorized defensive review of C/C++ packet-parser code. It looks for risky copy operations, signed length variables, unchecked length multiplication, and network-facing parser entry points.

## Run it

From the repository root, with the project virtual environment active:

```bash
python -m jenefar.voip_security path/to/parser.c
python -m jenefar.voip_security path/to/parser.cpp --json
python -m pytest -q tests/test_voip_security.py
```

The analyzer reads a local source file only. It does not scan a remote application, send SIP/WebRTC/SRTP packets, craft exploit payloads, execute shellcode, access device sensors, or erase telemetry.

## Recommended defensive workflow

1. **Scope and inventory:** document the app/library version and confirm authorization to review its source or test build.
2. **Parser review:** inspect findings manually; trace untrusted packet lengths from input to allocations, indexing, and copy operations.
3. **Boundary validation:** reject truncated headers, negative lengths, oversized payloads, and arithmetic overflow before allocation or copying.
4. **Safe fuzzing:** run an established coverage-guided fuzzer against a local test build in an isolated disposable environment, using synthetic inputs and resource limits.
5. **Crash triage:** preserve the reproducer and crash logs, identify the root cause, and add a regression test. Do not delete forensic evidence.
6. **Mitigation and verification:** patch the parser, enable compiler hardening/sanitizers where supported, rerun regression tests, and document the fixed version.

## Rules and limitations

- `VOIP001`: `memcpy` length requires a provable destination bound.
- `VOIP002`: signed size/length/count declarations require validation review.
- `VOIP003`: size-related multiplication may overflow.
- `VOIP004`: parser entry point merits manual boundary review.

These are heuristic signals, not CVE detection and not proof of exploitability. False positives are possible, and no findings does not prove the code is safe. The tool intentionally does not attempt remote discovery, exploit delivery, code execution, surveillance, command-and-control, or log wiping.
