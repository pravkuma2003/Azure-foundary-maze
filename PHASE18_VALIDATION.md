# Phase 18 Validation

## Expected Result

```text
Maze A shows feedback controls for Worker Agent A.
Maze B shows feedback controls for Worker Agent B.
Thumbs Up / Thumbs Down can be submitted independently per maze.
Feedback does not call an LLM and does not alter Worker behavior.
/api/feedback logs a structured MazeFeedback record to Application Insights.
If a run id exists, the same feedback is appended to durable Team Memory.
```

## Validation Plan

```text
1. Verify the hosted HTML contains the feedback controls and /api/feedback call.
2. Generate a fresh mission.
3. Submit thumbs-down feedback for Maze B.
4. Confirm /api/feedback returns status=recorded.
5. Confirm app_insights_logged=true.
6. Confirm team_memory_persisted=true when the run has durable Team Memory.
7. Confirm no LLM call count changes because feedback is telemetry-only.
```

## Live Validation

```text
Hosted HTML contains /api/feedback, Thumbs Up, Thumbs Down, feedback-note,
and Human Feedback Telemetry strings.

/api/mission returned:
phase: 18
concept: Human Feedback Telemetry
run_id: phase18-d73a0525e86d4b78
workflow_stage: mission_ready
worker_a_llm_calls: 0
worker_b_llm_calls: 0

/api/feedback returned:
status: recorded
event_name: MazeFeedback
app_insights_logged: true
team_memory_persisted: true
maze_id: maze_b
worker: Worker Agent B
rating: down

/api/memory confirmed:
backend: Azure Blob Storage
feedback.events: 1
latest feedback event: MazeFeedback for Maze B / Worker Agent B / down

Application Insights query confirmed:
timestamp: 2026-08-27T22:52:30Z
message starts with: MazeFeedback
phase: 18
run_id: phase18-d73a0525e86d4b78
rating: down

Loop guard follow-up:
Local hosted-agent package validation confirmed a solvable maze reaches
goal_reached in step mode without repeated-edge oscillation, and a
reachable-but-unsolved blocked maze ends as reported_impossible after
exhausting reachable cells through Worker-local visited/path_stack/dead_ends
state. This is not a precomputed route from the Maze Tool.

Live follow-up:
Worker Agent A and Worker Agent B were redeployed as version 10 with the
Worker-local exploration guard. The WebUI coordinator was redeployed with
Phase 18 parallel tick grouping, Loop guard summary display, and non-destructive
Foundry session reuse. A live run confirmed:
phase: 18
run_id: phase18-7827014d296a4d1d
Worker A outcome after tick 1: reported_impossible
Worker B outcome after tick 2: running
Worker B calls after tick 2: 2
Worker B reused the same Foundry agent_session_id across ticks.
```
