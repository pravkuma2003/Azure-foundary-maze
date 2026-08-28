# Phase 4: Tool Ownership

## Learning Objective

Show that prompts alone do not define an agent boundary. A role becomes
operationally different when the runtime gives it different tools.

## Previous Limitation

Phase 3 separated planning ownership:

```text
Analyst Agent owns global planning.
Worker Agent A owns Maze A local planning and moves.
```

That boundary was still mostly a contract. Phase 4 turns it into capability.

## New Concept

Role-specific tools.

```text
Analyst Agent v3
  allowed: read_team_memory, write_global_plan, estimate_workload, assign_task
  denied: inspect_maze_cell, list_legal_moves, move

Worker Agent A v3
  allowed: inspect_maze_cell, list_legal_moves, move, report_local_result
  denied: write_global_plan, estimate_workload, assign_task
```

## Architecture

```text
Analyst Agent
  -> uses Pydantic AI
  -> owns planning tools only
  -> cannot move in the maze

Team Memory
  -> stores global plan and assignment

Orchestrator
  -> deterministic dispatcher
  -> routes allowed assignments

Worker Agent A
  -> uses Pydantic AI
  -> owns Maze A tool use
  -> cannot assign global work

Maze Tool
  -> validates legal moves and wall checks
```

## What This Phase Should Not Do

```text
Do not introduce Worker Agent B.
Do not add local memory yet.
Do not make the Orchestrator intelligent.
Do not change the maze, goal, or call budget.
Do not optimize communication yet.
```

## Result Observed

```text
Reasoning agents: 2
Analyst LLM calls: 1
Worker Agent A LLM calls: 1
Orchestrator LLM calls: 0
Denied cross-role tool calls: 2
Tool boundary enforced: true
```

## Knowledge Check

1. Why is a prompt instruction weaker than a tool allowlist?
2. Which tools belong to the Analyst?
3. Which tools belong to Worker Agent A?
4. Why should the Analyst not call `move`?
5. Why should Worker Agent A not call `assign_task`?
