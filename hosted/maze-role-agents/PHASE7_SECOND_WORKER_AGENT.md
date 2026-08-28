# Phase 7: Second Worker Agent

## Learning Objective

Introduce a second LLM Worker only after one Worker Agent's tools, local memory,
and synchronization responsibilities are clear.

## Previous Limitation

Phase 6 proved that Worker Agent A can own a full local reasoning loop:

```text
Maze A tools
Worker Local Memory
sync decisions
promoted discoveries
```

Maze B was still handled by a deterministic worker. Phase 7 promotes that worker
into Worker Agent B.

## New Concept

Multiple reasoning Workers.

```text
Worker Agent A
  owns Maze A only
  uses Maze A tools
  keeps Worker Local Memory A
  promotes Maze A discoveries to Team Memory

Worker Agent B
  owns Maze B only
  uses Maze B tools
  keeps Worker Local Memory B
  promotes Maze B discoveries to Team Memory
```

## Architecture

```text
Analyst Agent
  -> uses Pydantic AI
  -> assigns Maze A to Worker Agent A
  -> assigns Maze B to Worker Agent B

Orchestrator
  -> deterministic dispatcher
  -> routes assignments only

Worker Agent A
  -> uses Pydantic AI
  -> owns Maze A local reasoning
  -> makes one LLM decision call per Maze A move

Worker Agent B
  -> uses Pydantic AI
  -> owns Maze B local reasoning
  -> makes one LLM decision call per Maze B move

Team Memory
  -> receives promoted discoveries from both Workers
```

## What This Phase Should Not Do

```text
Do not make the Orchestrator intelligent.
Do not let workers collaborate yet.
Do not let Worker Agent A inspect Maze B.
Do not let Worker Agent B inspect Maze A.
Do not introduce conflict resolution yet.
```

## Result Observed

```text
Reasoning agents: 3
Analyst LLM calls: 1
Worker Agent A LLM calls: 8
Worker Agent B LLM calls: 8
Orchestrator LLM calls: 0
Total LLM calls: 17 / 25
Worker local memories: 2
Deterministic workers: 0
```

Each Worker Agent makes fresh local decisions during execution. The Worker does
not receive the full route in one setup call.

## Knowledge Check

1. Why was Worker Agent B not introduced earlier?
2. What does Worker Agent B own?
3. What does Worker Agent B not own?
4. Why does the Orchestrator remain deterministic?
5. What new problem appears once two Worker Agents exist?
