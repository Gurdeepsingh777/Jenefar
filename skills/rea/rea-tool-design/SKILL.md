---
name: rea_tool_design
version: "1.0"
description: Design or change Jenefar/REA tools, API schemas, MCP contracts and evidence/result semantics.
keywords:
  - tool design
  - MCP contract
  - API schema
  - tool schema
  - connector design
  - evidence semantics
  - REA
connectors:
  - github
  - rea
permissions:
  - repository_read
  - evidence_based_analysis
enabled_by_default: true
---
# REA Tool Design

Use for a requested tool/connector design or implementation affecting tool boundaries, API/MCP contracts, provider capabilities, or evidence semantics.

1. Inspect the current contract and nearest existing tool that answers the analyst's question. Compare source, docs and live advertised schemas where available.
2. Describe the smallest useful boundary, typed inputs, validation, result shape, error states, evidence identity/coverage and nearest alternative.
3. Define user-visible behavior for unavailable providers, malformed input, partial findings, cancellation and failures.
4. For implementation, identify affected consumers and tests and preserve generated-file ownership and existing authorization.
5. Verify the public entry point, result contract, error path and focused consumer/provider tests. Clearly separate mocks from real-provider checks.
6. Report changed files, verification, migration needs and remaining uncertainty.

This skill does not grant permission to execute targets, install software, publish, push or merge.
