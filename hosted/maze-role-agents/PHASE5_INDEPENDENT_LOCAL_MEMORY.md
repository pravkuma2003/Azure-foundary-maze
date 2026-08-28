# Phase 5: Independent Local Memory

## Learning Objective

Teach that not every observation belongs in Team Memory. A Worker Agent needs
private memory for temporary, local execution details.

## Previous Limitation

Phase 4 enforced role-specific tools:

```text
Analyst Agent can plan and assign.
Worker Agent A can inspect and move in Maze A.
```

But every remembered fact still had one obvious place: Team Memory. That is too
broad for step-level navigation details.

## New Concept

Local vs shared memory.

```text
Worker Local Memory
  private to Worker Agent A
  stores visited cells
  stores legal moves inspected
  stores rejected backtracks
  stores local route notes

Team Memory
  shared by the team
  stores assignment
  stores goal
  stores completion summary
  stores blocked/escalation facts
```

## Architecture

```text
Analyst Agent
  -> uses Pydantic AI
  -> defines shared-memory policy

Team Memory
  -> stores mission-level facts only

Orchestrator
  -> deterministic dispatcher

Worker Agent A
  -> uses Pydantic AI
  -> uses Maze A tools
  -> writes detailed route state to Worker Local Memory
  -> publishes only useful summaries to Team Memory

Worker Local Memory
  -> deterministic private state
  -> visible to Worker Agent A only
```

## What This Phase Should Not Do

```text
Do not introduce Worker Agent B.
Do not synchronize local discoveries yet.
Do not optimize communication yet.
Do not make Orchestrator intelligent.
Do not change the maze, goal, or call budget.
```

## Result Observed

```text
Reasoning agents: 2
Analyst LLM calls: 1
Worker Agent A LLM calls: 1
Orchestrator LLM calls: 0
Worker Local Memory components: 1
Team Memory writes: assignment and completion summary
Local Memory writes: step-level route observations
```

## Knowledge Check

1. Why should visited cells stay local?
2. What should Team Memory receive?
3. What should Worker Agent A publish when it succeeds?
4. What should Worker Agent A publish when it is blocked?
5. Why does local memory come before synchronization?
