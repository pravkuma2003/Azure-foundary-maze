# Phase 6: Shared Knowledge Synchronization

## Learning Objective

Teach when a Worker Agent should promote private local memory into shared Team
Memory.

## Previous Limitation

Phase 5 added private Worker Local Memory:

```text
Worker Local Memory stores step-level navigation facts.
Team Memory stores mission-level facts.
```

But local memory can hide useful facts from the rest of the team. Phase 6 adds a
synchronization rule.

## New Concept

Synchronization.

```text
Retain locally:
  routine visited-cell notes
  temporary rejected backtracks
  single-step legal move checks
  route candidates that do not affect the team

Promote to Team Memory:
  assignment acceptance
  route viability checkpoint
  blocked or escalation state
  completion summary
```

## Architecture

```text
Analyst Agent
  -> uses Pydantic AI
  -> defines synchronization policy

Worker Agent A
  -> uses Pydantic AI
  -> writes local observations
  -> evaluates whether each observation should stay local or become shared

Worker Local Memory
  -> retains detailed local navigation facts

Team Memory
  -> receives only promoted shared discoveries

Orchestrator
  -> deterministic dispatcher
```

## What This Phase Should Not Do

```text
Do not introduce Worker Agent B.
Do not add collaboration yet.
Do not make Orchestrator intelligent.
Do not publish every local observation.
Do not change the maze, goal, or call budget.
```

## Result Observed

```text
Reasoning agents: 2
Analyst LLM calls: 1
Worker Agent A LLM calls: 1
Orchestrator LLM calls: 0
Synchronization evaluations: 9
Promoted discoveries: 3
Retained local discoveries: 6
```

## Knowledge Check

1. What makes a local discovery worth promoting?
2. Why should routine visited cells stay local?
3. What is the cost of publishing too much to Team Memory?
4. What should be published when a Worker is blocked?
5. Why should synchronization be learned before adding another Worker Agent?
