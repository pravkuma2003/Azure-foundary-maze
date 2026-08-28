# Phase 3: Global vs Local Planning

## Learning Objective

Separate Analyst global planning from Worker Agent local planning.

## Previous Limitation

Phase 2 introduced Worker Agent A, but the planning boundary was still informal:

```text
Analyst assigns Maze A.
Worker Agent A plans locally.
```

Phase 3 makes that boundary explicit.

## New Concept

Planning boundaries.

```text
Analyst Agent
  owns mission constraints
  owns task assignment
  does not choose step-by-step Maze A moves

Worker Agent A
  owns Maze A local route planning
  owns local move choices
  does not change the mission or assign workers
```

## Architecture

```text
Analyst Agent
  -> writes global planning contract
  -> uses Pydantic AI

Team Memory
  -> stores the contract and ownership boundary

Orchestrator
  -> dispatches the contract
  -> deterministic

Worker Agent A
  -> reads the contract
  -> creates local route plan
  -> uses Maze Tool
  -> uses Pydantic AI
```

## What This Phase Should Not Do

```text
Do not introduce Worker Agent B.
Do not give Analyst step-by-step Maze A route ownership.
Do not make Orchestrator intelligent.
Do not change tools yet.
Do not introduce collaboration or conflict resolution.
```

## Result Observed

```text
Reasoning agents: 2
Analyst LLM calls: 1
Worker Agent A LLM calls: 1
Global planning owner: Analyst Agent
Local planning owner: Worker Agent A
Analyst step-by-step moves: 0
Worker local route steps: 8
```

## Knowledge Check

1. What does Analyst own in Phase 3?
2. What does Worker Agent A own in Phase 3?
3. Why should Analyst not provide step-by-step Maze A moves?
4. Why does Orchestrator remain deterministic?
5. What does Phase 4 need to enforce with tools?
