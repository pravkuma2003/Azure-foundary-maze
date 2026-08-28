# Phase 2: Worker Agent

## Learning Objective

Convert one deterministic worker into an LLM reasoning agent with Maze tools.

## New Concept

```text
LLM + Tool = Agent
```

In Phase 1, the Analyst owned both global and local reasoning.

In Phase 2, Worker A becomes:

```text
Worker Agent A
  LLM reasoning
  Maze Tool access
  local navigation ownership
```

## Architecture

```text
Analyst Agent
  owns global assignment
  uses Pydantic AI

Worker Agent A
  owns Maze A local navigation
  uses Pydantic AI
  uses Maze Tool

Worker Program B
  remains deterministic
  executes prepared Maze B route

Orchestrator
  remains deterministic
  dispatches assignments
```

## Boundary

Analyst does not choose each Maze A move.

Worker Agent A does not partition the whole mission.

That boundary matters:

```text
Analyst = global assignment
Worker Agent A = local navigation
```

## What This Phase Should Not Do

```text
Do not introduce Worker Agent B yet.
Do not make Orchestrator intelligent.
Do not add collaboration.
Do not add conflict resolution.
Do not change the maze.
```

## Result Observed

```text
Reasoning agents: 2
Analyst LLM calls: 1
Worker Agent LLM calls: 1
Orchestrator LLM calls: 0
Deterministic workers remaining: 1
```

Worker Agent A uses Maze Tool events:

```text
inspect legal moves
choose local move
move validation
```

## Knowledge Check

1. Why is Worker Agent A now a real reasoning agent?
2. What does Analyst still own?
3. What does Worker Agent A now own?
4. Why does Worker Program B remain deterministic?
5. Why should Phase 3 focus on global vs local planning?
