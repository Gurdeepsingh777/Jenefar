# Jenefar Intelligence Layer

Date: 2026-10-23
Status: approved
Approach: A — Intelligence layer on the existing orchestrator

## Goal

Make Jenefar more powerful without rewriting the agent runtime. Reliability first, then smarter answers, then cost/speed. Authorized workspace inspect/edit/run becomes auto; GUI, security, robot, and terminal stay gated.

Success bar: harder tasks complete more reliably, answers are better checked, simple turns stay on a cheap/fast model.

## Current gaps

- Planner is keyword-only. Complex or mixed requests can route to the wrong specialist.
- `ModelRouter` falls back to a single `OPENAI_MODEL` for every unset role. Hard and easy work share the same model.
- `Verifier` only rejects empty strings. No reflection, no replan.
- Default tool loop is 4 rounds (local development already 20). No complexity-based budget.
- One request maps to one agent. Specialists do not collaborate.
- Workspace edits are already non-critical when confirmation is off; this design makes that policy explicit and keeps high-impact tools gated.

## Architecture

Existing wake word, session, keyword planner, agent router, tool broker, provider pool, self-heal, audit, and scope stay in place. Four modules sit on that path:

```text
User
  -> Wake/session (existing)
  -> Planner (keyword, existing)
  -> ComplexityClassifier   [NEW]  uses text + plan (is_compound, needs_tool, agent)
       | plan.confidence < 0.75
       v
  -> LLMIntentFallback      [NEW]  if agent changes, re-classify once
  -> ModelRouter            [UPGRADE]  role + complexity
  -> Specialist + ToolBroker (existing)
  -> AdaptiveAutonomy       [POLICY]   workspace auto; GUI/security/network gated
  -> Critic/Reflect         [UPGRADE]  one replan on fail
  -> Response
```

Rules:

- Keyword planner always runs first. It is cheap and deterministic.
- Classifier is heuristic-first and sees the plan. A fast model is used only when the heuristic is uncertain.
- LLM intent fallback runs only on low planner confidence. If it changes the agent, complexity is recomputed once from the new plan.
- Critic allows at most one replan.
- `authorized_targets`, JSONL audit, and GUI/security/network confirmation do not change.
- Workspace inspect/edit/run inside authorized roots is auto when `require_confirmation` is false. Backup and diff stay as they are.

## Components

### 1. ComplexityClassifier (`jenefar/core/complexity.py`)

Returns `simple | standard | hard`.

Heuristic signals: text length, keywords (`fix`, `implement`, `debug`, `plan`, `kali`, multi-file markers), planner `is_compound`, `needs_tool`.

- `simple`: greetings, time, short Q, one-step lookup
- `standard`: single-file edit, one research query, one tool
- `hard`: multi-file, debug+fix, security, long research, compound plans

If the heuristic is uncertain, a fast-model JSON classify is allowed. Any classifier failure yields `standard`.

### 2. LLMIntentFallback (`jenefar/core/intent.py`)

Runs only when `plan.confidence < 0.75`.

Fast model returns JSON `{intent, agent, needs_tool, reason}`. Agent must be in the allowlist used by `AgentRouter`. Bad JSON, unknown agent, or timeout keeps the original keyword plan.

### 3. ModelRouter upgrade (`jenefar/core/model_router.py`)

Selection is role plus complexity:

| complexity | default role | env override |
|---|---|---|
| simple | `fast` | `JENEFAR_MODEL_FAST` |
| standard | agent role | existing `JENEFAR_MODEL_*` |
| hard | `reasoning` if set, else agent role | `JENEFAR_MODEL_REASONING` |

Hard coding tasks (`local_development`, `python`, `repository`) prefer `JENEFAR_MODEL_CODING` over generic reasoning. An explicit agent model still wins. Provider failover in `ProviderPool` is unchanged.

### 4. Critic (`jenefar/critic/verifier.py`)

Replace the empty-string stub. Fast model (or a deterministic checklist when offline) reviews:

- empty / "I don't know" without trying tools
- claimed file, screen, or web result without matching tool output
- ignored tool error
- clearly unfinished task

Behavior:

- `simple` tasks skip the critic
- fail + `critic_pass == 0` → one replan with `critic_notes` in metadata
- pass, or second fail → return the result; on second fail append a short "could not verify" note
- critic exception or unavailable model → pass through the original result

### 5. Adaptive autonomy (policy, not a new runtime)

When `require_confirmation` is false, workspace tools stay non-critical:

- `workspace_inspect_file`, `workspace_list_directory`
- `workspace_edit_file`, `workspace_create_file`
- `workspace_validate_python`, `workspace_run_python`, `workspace_run_pytest`

Still critical / gated: GUI, security/Kali, robot, MQTT/ROS2, `connector_execute`, terminal. Paths outside `WorkspacePolicy` roots remain denied. Every invocation still writes the audit log.

### 6. Tool-loop budget

`max_tool_rounds` by complexity, capped at 20 (existing LLM loop cap):

- simple: 4
- standard: 8
- hard: 16
- `LocalDevelopmentAgent` keeps 20

Repeated tool-signature detector is unchanged.

## Data flow

```text
handle(text)
  1. existing shortcuts (time, window, screen, confirmation)
  2. plan = Planner.plan(text)
  3. complexity = Classifier.classify(text, plan)
  4. if plan.confidence < 0.75:
       plan = IntentFallback.refine(text, plan) or plan
       complexity = Classifier.classify(text, plan)
  5. model_role = Router.resolve(plan.agent, complexity)
  6. metadata += {complexity, model_role, plan, critic_pass: 0}
  7. result = Router.dispatch(text, metadata)
  8. if complexity != simple:
       critique = Critic.review(task, result, tool_trace)
       if critique.fail and critic_pass == 0:
           metadata.critic_notes = critique.notes
           metadata.critic_pass = 1
           goto 7 once
  9. existing session / memory / eval / trace
```

`handle()` never raises because of the new modules. Each module is wrapped in try/except.

## Error handling

| failure | behavior |
|---|---|
| Classifier fail | `standard` |
| IntentFallback timeout / bad JSON / unknown agent | original keyword plan |
| Critic unavailable / exception | original result |
| Critic fail after replan | original result + short verify note |
| Provider fail | existing cooldown + next provider + local fallback |
| Path outside workspace | existing `WorkspacePolicy` error |
| GUI / security / robot / terminal | existing approval + `authorized_targets` |
| Repeated tool signature | existing loop stop |

## Observability

`ExecutionTrace` / evaluation records:

- `complexity`
- `planner_confidence`
- `intent_fallback_used`
- `model_role`, `model`, `provider`
- `critic_verdict`, `critic_replan`

Visible via `--evaluation-report`.

## Testing

Unit:

- `tests/test_complexity.py`
- `tests/test_intent_fallback.py`
- extend `tests/test_model_router.py`
- `tests/test_critic.py`
- `tests/test_adaptive_autonomy.py`

Integration:

- low-confidence plan triggers mocked fallback
- hard task: critic fail causes exactly one replan
- trace contains complexity, model_role, critic_verdict
- provider failover still passes

Regression: full `tests/` suite. Wake word, broker scope, workspace backup/diff, self-heal, Hinglish, avatar stay untouched except `handle()` wiring.

## Out of scope

- ReAct / full agent-runtime rewrite
- Parallel multi-agent collaboration
- Parallel tool execution
- New LLM providers
- Wake-word / TTS / avatar UI changes
- Cost/token billing UI

## Files expected to change

- `jenefar/core/complexity.py` (new)
- `jenefar/core/intent.py` (new)
- `jenefar/core/model_router.py`
- `jenefar/core/orchestrator.py`
- `jenefar/core/llm.py` (optional: expose complexity to round budget)
- `jenefar/agents/llm_agent.py` (complexity-aware `max_tool_rounds`, critic notes in prompt)
- `jenefar/critic/verifier.py`
- `jenefar/evaluation/trace.py` (new fields)
- tests listed above
- `.env.example` comments for `JENEFAR_MODEL_FAST` / `JENEFAR_MODEL_REASONING` if missing
