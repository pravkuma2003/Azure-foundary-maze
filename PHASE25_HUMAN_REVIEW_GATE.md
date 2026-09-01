# Phase 25 - Human Review Gate

## Objective

Use the Reviewer Agent output as a controlled decision gate.

Phase 24 made the review visible. Phase 25 records what the learner decides to
do with that review:

```text
accept the review
or
request retry planning
```

This phase does not automatically retry any Worker. The lesson is governance:
an evaluator can recommend, but a human or policy gate decides whether the next
workflow step is allowed.

## Runtime Flow

```text
Workers reach terminal outcomes
  -> Reviewer Agent evaluates the run
  -> WebUI shows score, threshold, retry target, and findings
  -> learner records a gate decision
  -> WebUI writes gate decision to Team Memory
  -> WebUI logs gate decision to Application Insights
```

## New UI Controls

The Review panel now includes:

```text
Accept Review
Request Retry Planning
```

Both buttons are deliberately simple. They capture intent but do not execute a
retry yet.

## Data Captured

Each gate decision is logged as:

```text
event_name: MazeReviewGate
phase: 25
gate_schema: review_gate_v1
run_id
decision: accepted | retry_requested
review_status
review_score
review_threshold
retry_target
human_gate
worker_a_outcome
worker_b_outcome
created_at
```

## Team Memory Writes

The WebUI writes:

```text
review.gate.latest
review.gate.status
review.gate.decisions
```

This keeps the decision durable and queryable without adding another Azure
service.

## Learning Boundary

Phase 25 teaches evaluation-gated workflow.

It does not yet teach:

```text
automatic Worker retry
Reviewer-driven prompt edits
multi-run comparison
quality dashboards
deployment rollback
```

Those belong in later phases.
