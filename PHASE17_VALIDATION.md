# Phase 17 Validation

## Expected Result

```text
Run Fresh Maze still calls only the Analyst.
Play dispatches active Worker steps through /api/worker-steps.
Worker A and Worker B reason concurrently when both are active.
Each Worker has its own 50-call LLM budget.
Worker A exhausting its limit does not block Worker B, and Worker B exhausting
its limit does not block Worker A.
Team Memory keeps accumulated Worker step history.
The maze timeline grows incrementally after each parallel tick.
Learner view shows one combined Parallel Tick event for both Worker moves.
The deterministic WebUI Coordinator does not make LLM calls.
```

## Validation Plan

```text
1. Verify hosted WebUI serves /api/worker-steps JavaScript.
2. Create a fresh Analyst mission.
3. Call /api/worker-steps with roles ["worker_a", "worker_b"].
4. Confirm one merged trace returns for the same Team Memory run.
5. Confirm parallel_worker_step_execution is true.
6. Confirm prior Worker events are accumulated across repeated ticks.
7. Confirm the WebUI reports Worker A and Worker B LLM calls separately.
8. Confirm /api/worker-steps filters only the worker whose own 50-call budget is exhausted.
```

## Live Result

```text
status: complete
webui_url: https://maze-webui-func-prav-ada483.azurewebsites.net/
mission_phase: 17
mission_workflow_stage: mission_ready
mission_llm_calls: 1
parallel_endpoint: /api/worker-steps
tick_1_elapsed_s: 11.8
tick_1_roles: worker_a, worker_b
tick_1_llm_calls_total: 3
tick_1_move_events: 2
tick_1_parallel_tick_events: 1
tick_1_parallel_tick_move_count: 2
tick_1_parallel_tick_detail: Worker Agent A moved east on Maze A: (0, 0) -> (0, 1). Worker Agent B moved south on Maze B: (0, 0) -> (1, 0).
tick_2_elapsed_s: 12.1
tick_2_roles: worker_a, worker_b
tick_2_llm_calls_total: 5
tick_2_move_events: 4
worker_a_outcome_after_tick_2: running
worker_b_outcome_after_tick_2: running
worker_llm_call_budget: 50 per worker
team_memory_run_id_prefix: phase17
browser_secret_exposure: none detected
```

## Per-Worker Budget Update

```text
validated: 2026-08-27
webui_cache_buster: ?v=phase17-per-worker-budget
html_has_worker_a_calls: true
html_has_worker_b_calls: true
mission_budget_scope: per_worker
mission_worker_budget: 50
mission_worker_a_calls: 0
mission_worker_b_calls: 0
worker_step_source: foundry-parallel-worker-steps
worker_step_budget_scope: per_worker
worker_step_worker_budget: 50
worker_step_worker_a_calls: 1
worker_step_worker_b_calls: 1
worker_step_roles_this_tick: worker_a, worker_b
```

## Peer Review Follow-Up

```text
review_requested: peer agent review of Phase 17 Azure WebUI + hosted role-agent code
critical_fix_1: durable Team Memory no longer silently falls back to request-local memory unless TEAM_MEMORY_BACKEND=request is explicitly configured
critical_fix_2: 50-call limit is now hard-capped per Worker by passing remaining role budget into the hosted Worker and reducing PydanticAI UsageLimits
major_fix_1: /api/worker-steps now preserves one Worker's successful step when the other Worker call fails
major_fix_2: filtered-role completion now checks both Worker outcomes before reporting workers_complete
major_fix_3: model-controlled UI text is escaped and maze rows are validated
speed_fix_1: WebUI managed identity token is cached per warm Function process
speed_fix_2: hosted role-agent Foundry token is cached per warm hosted-agent process
speed_fix_3: parallel tick Team Memory updates are batched into one grouped write
```

## Peer Review Live Validation

```text
validated: 2026-08-27
webui_cache_buster: ?v=phase17-peer-review-fixes
html_has_escape_function: true
html_has_worker_counters: true
html_has_parallel_endpoint: true
mission_phase: 17
memory_backend: Azure Blob Storage
fallback_error: None
mission_budget_scope: per_worker
mission_worker_budget: 50
worker_step_source: foundry-parallel-worker-steps
worker_step_phase: 17
worker_step_budget_scope: per_worker
worker_step_worker_budget: 50
worker_step_worker_a_calls: 1
worker_step_worker_b_calls: 1
worker_step_worker_a_outcome: running
worker_step_worker_b_outcome: running
worker_step_roles_this_tick: worker_a, worker_b
parallel_tick_events: 1
local_edge_case_tests: per-worker filtering and partial-failure persistence passed
```
