---
name: rea_ci_tests_audit
version: "1.0"
description: Audit CI and tests for false passes, fixture drift, missing coverage and measured test costs.
keywords:
  - CI audit
  - test audit
  - pytest
  - regression test
  - fixture drift
  - false pass
  - test coverage
  - REA
connectors:
  - github
  - rea
permissions:
  - repository_read
  - evidence_based_analysis
enabled_by_default: true
---
# REA CI and Test Audit

Use for suite/workflow investigations or efficiency changes, rather than replacing ordinary focused feature testing.

1. Pin the inspected branch, commit SHA, workflows and test commands. Establish a baseline before editing.
2. Map each important assertion and gate to the production behavior it is intended to protect. Check source, fixtures, tool versions and current contracts for drift.
3. Reproduce suspicious failures or green-but-ineffective tests using the smallest meaningful test. Verify that the test detects a controlled regression when safe to do so.
4. Separate fake-provider/unit evidence from real engine or end-to-end evidence. Record prerequisites, skips, timeout and environment.
5. Make targeted fixes without weakening safety or assertions. Rerun the focused checks; run the full suite only when uncertainty or scope justifies it.
6. Report exact commands, revision, exit status, failures, skip reasons, coverage gaps and remaining unknowns.

Do not infer that a failure is fixed because a retry passed. A test audit does not authorize publishing, pushing, merging or changing unrelated configuration.
