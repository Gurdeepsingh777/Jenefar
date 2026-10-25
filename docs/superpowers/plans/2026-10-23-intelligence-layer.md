# Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add complexity classification, LLM intent fallback, complexity-aware model routing, a real critic with one replan, workspace auto-policy lock, and tool-round budgets on the existing Jenefar orchestrator.

**Architecture:** Keyword planner stays first. Classifier reads text + plan. Low-confidence plans may be refined by a fast-model JSON fallback. ModelRouter takes role + complexity. Critic reviews non-simple results and allows one replan. Workspace tools stay non-critical; terminal/security/robot/connector stay critical.

**Tech Stack:** Python 3.10+, pytest, existing `LLMClient` / `ProviderPool` / `Planner` / `ToolBroker`.

## Global Constraints

- Heuristic-first; LLM only on uncertain classify or planner confidence < 0.75.
- Critic: skip `simple`; max one replan; exceptions pass through.
- `handle()` never raises because of new modules (try/except each).
- Workspace auto inside authorized roots when `require_confirmation` is false.
- GUI/security/robot/terminal/connector stay gated via existing critical/screen policy.
- No new providers, no ReAct rewrite, no parallel tools, no avatar/TTS changes.
- TDD: failing test first, then minimal production code.
- Do not commit unless the user asks.

## File map

- Create: `jenefar/core/complexity.py`
- Create: `jenefar/core/intent.py`
- Modify: `jenefar/core/model_router.py`
- Modify: `jenefar/critic/verifier.py`
- Modify: `jenefar/core/orchestrator.py`
- Modify: `jenefar/agents/llm_agent.py`
- Modify: `jenefar/evaluation/trace.py`
- Modify: `.env.example` (comments only)
- Tests: `tests/test_complexity.py`, `tests/test_intent_fallback.py`, `tests/test_critic.py`, `tests/test_adaptive_autonomy.py`, `tests/test_intelligence_orchestrator.py`, extend `tests/test_model_router.py`

---

### Task 1: ComplexityClassifier

**Files:**
- Create: `jenefar/core/complexity.py`
- Test: `tests/test_complexity.py`

**Interfaces:**
- Produces: `Complexity = Literal["simple", "standard", "hard"]`
- Produces: `ComplexityResult(level, source, reason)`
- Produces: `ComplexityClassifier(llm_complete=None).classify(text: str, plan=None) -> ComplexityResult`
- Produces: `tool_round_budget(complexity: str, agent_max: int = 4) -> int`

- [ ] Tests then implementation as specified in the design spec (heuristic-first, LLM only if uncertain, fail -> standard, tool budgets simple=4/standard=8/hard=16, agent_max>=20 stays 20).

---

### Task 2: LLMIntentFallback

**Files:**
- Create: `jenefar/core/intent.py`
- Test: `tests/test_intent_fallback.py`

**Interfaces:**
- Consumes: `Planner.plan` / `Plan(intent, agent, needs_tool, confidence, reason)`
- Produces: `LLMIntentFallback(llm_complete=None, threshold=0.75).refine(text, plan) -> Plan`
- Produces: `ALLOWED_AGENTS` frozenset matching AgentRouter specialists
- Skip when confidence >= 0.75; invalid JSON / unknown agent / exception keeps original plan.

---

### Task 3: ModelRouter complexity

**Files:**
- Modify: `jenefar/core/model_router.py`
- Test: `tests/test_model_router.py`

**Interfaces:**
- Produces: `role_for_complexity(agent: str, complexity: str) -> str`
- Produces: `resolve(role, *, explicit_model=None, complexity=None) -> ModelSelection`
- simple -> fast; hard coding agents -> coding; hard others -> reasoning if `JENEFAR_MODEL_REASONING` set else agent role; explicit model still wins.

---

### Task 4: Critic / Verifier

**Files:**
- Modify: `jenefar/critic/verifier.py`
- Test: `tests/test_critic.py`

**Interfaces:**
- Produces: `Critique(passed: bool, notes: str, skipped: bool = False, source: str = "checklist")`
- Produces: `Verifier.review(task, result, *, complexity="standard", tool_trace=None) -> Critique`
- Produces: `Verifier.verify(task, result, *, complexity="standard", tool_trace=None, critic_pass=0) -> str` (backward compatible)
- simple skip; empty fail; claimed-without-tool fail; ignored tool error fail; exception -> pass-through; second fail appends verify note.

---

### Task 5: Adaptive autonomy lock

**Files:**
- Test: `tests/test_adaptive_autonomy.py`
- Modify `jenefar/tools/broker.py` only if tests prove a gap (workspace must stay non-critical; terminal/kali/security/robot/connector critical; outside-root denied).

---

### Task 6: Orchestrator + agent wiring

**Files:**
- Modify: `jenefar/core/orchestrator.py`
- Modify: `jenefar/agents/llm_agent.py`
- Modify: `jenefar/evaluation/trace.py`
- Test: `tests/test_intelligence_orchestrator.py`

Wire: plan -> classify -> optional intent fallback -> reclassify -> model_role -> dispatch -> critic review -> one replan. Trace fields: complexity, intent_fallback_used, critic_verdict, critic_replan. Agent uses `tool_round_budget` and injects critic notes.

---

### Task 7: Regression

Run `python -m pytest tests -q`. Fix any breakage. Update `.env.example` comments for complexity-aware `JENEFAR_MODEL_FAST` / `JENEFAR_MODEL_REASONING`.
