# Phase 17 - Parallel Worker Step Execution

## Objective

Let independent Worker agents make progress at the same time when their tasks do
not depend on each other.

## What Changed

Before:

```text
Play -> Worker A one step -> render
Play -> Worker B one step -> render
```

After:

```text
Play -> parallel tick
       -> Worker A one step
       -> Worker B one step
       -> merge both responses
       -> persist Team Memory
       -> render both maze updates
```

## Learning Point

The Orchestrator still does not need an LLM. It applies a deterministic rule:

```text
If a Worker is not terminal, include it in the next parallel tick.
If a Worker is terminal, do not call it again.
Do not exceed that Worker's own 50-call LLM budget.
```

The intelligence remains inside the Worker agents. The orchestration improvement
is concurrency, not extra reasoning.

The call limit is role-scoped, not shared. If Worker Agent A reaches 50 calls or
reports blocked, Worker Agent B can continue using its own remaining calls, and
vice versa.

## Boundary

The WebUI sends one request to `/api/worker-steps` per tick. That endpoint calls
the active hosted Worker agents concurrently and writes both results back to
durable Team Memory in a controlled order. This avoids two browser requests
writing to the same Team Memory blob at the same time.

The learner timeline is tick-based. It shows one `Parallel Tick` card per
coordinated execution window, and that card applies Worker A and Worker B moves
to the two mazes together. The lower-level per-worker decision and move events
remain available in the full trace for audit, but the learner view no longer
makes parallel work look serial.
