---
name: rea_analysis_optimization
version: "1.0"
description: Optimize analysis workflows for latency, CPU, memory and duplicate work while preserving evidence and correctness.
keywords:
  - analysis optimization
  - performance profiling
  - latency
  - memory profiling
  - cpu profiling
  - cache design
  - rea
connectors:
  - github
  - rea
permissions:
  - repository_read
  - evidence_based_analysis
enabled_by_default: true
---
# REA Analysis Optimization

Use this workflow for measured analysis bottlenecks, not speculative optimization.

1. Identify the user-visible task, evidence that must be preserved, relevant artifact, provider and baseline revision.
2. Trace one normal CLI/MCP request from public entry point to the actual producer and measure the phases that matter.
3. Locate the earliest unnecessary work. Prefer fixing the owning layer over adding a second cache, index, adapter or orchestration layer.
4. Define an independent correctness oracle. Preserve source identity, address widths, alternatives, unresolved endpoints, coverage, evidence links and meaningful unknowns.
5. Compare equivalent completed work with relevant small/large cases. Include time, memory and extra tool/catalog calls when they affect the task.
6. Change only what measurements support. Report costs removed, residual costs, verification commands and limits of the evidence.

Do not claim a speedup based only on fewer returned fields if the full report was still computed. This skill does not authorize publishing, pushing, merging or executing new targets. Keep existing permissions and approval boundaries.
