# Phase 18 - Human Feedback Telemetry

## Objective

Capture simple human feedback about each Worker Agent without changing agent
behavior yet.

## What Changed

Each maze card now has feedback controls for the Worker assigned to that maze:

```text
Maze A -> Worker Agent A -> Thumbs Up / Thumbs Down
Maze B -> Worker Agent B -> Thumbs Up / Thumbs Down
```

The learner can add an optional short note. The feedback does not change the
current run, route, prompt, or memory policy.

## Telemetry Boundary

The WebUI posts feedback to `/api/feedback`. The Azure WebUI Function records a
structured log entry:

```text
event_name: MazeFeedback
feedback_schema: thumbs_v1
phase: 18
run_id
maze_id
maze_label
worker
rating: up | down
note
worker_a_calls
worker_b_calls
worker_a_outcome
worker_b_outcome
workflow_stage
created_at
```

Because the WebUI Function is connected to Application Insights, this log flows
to the shared Log Analytics workspace as a trace. When a Team Memory run id is
available, the same feedback event is also appended to `feedback.events` in
durable Team Memory.

## Learning Point

This phase separates observation from adaptation:

```text
Human gives feedback -> telemetry is captured -> agents do not change yet
```

Later phases can use this feedback for reports, quality scoring, prompt
improvement, or reinforcement-style evaluation.

## Follow-up: Worker Loop Feedback

A learner run showed the expected value of this feedback path: Worker B repeated
between the same cells and Worker A also spent calls on already-exhausted moves.
The fix keeps the Maze Tool deterministic and non-planning, but gives each
Worker stronger local exploration memory:

```text
visited cells
active path_stack
dead_ends
productive_unvisited_moves
backtrack_move
guardrail_corrections
```

The Worker LLM still chooses the next move, but the runtime now prevents obvious
oscillation: if an unvisited legal move exists, a visited/dead-end move is
corrected; if every local exit is exhausted, the Worker backtracks; if no
backtrack remains, it reports the maze impossible. This is local exploration
bookkeeping, not a route solver.

## Example

```text
rating: down
maze_id: maze_b
worker: Worker Agent B
note: Worker B repeated between (0,2) and (0,3) before finding the route.
```

## Log Analytics Query

```kusto
traces
| where message startswith "MazeFeedback "
| extend payload = parse_json(substring(message, strlen("MazeFeedback ")))
| project timestamp,
          run_id=tostring(payload.run_id),
          maze_id=tostring(payload.maze_id),
          worker=tostring(payload.worker),
          rating=tostring(payload.rating),
          note=tostring(payload.note),
          worker_a_calls=toint(payload.worker_a_calls),
          worker_b_calls=toint(payload.worker_b_calls),
          workflow_stage=tostring(payload.workflow_stage)
| order by timestamp desc
```
