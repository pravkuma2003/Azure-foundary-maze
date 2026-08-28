# Phase 13 - Independent Foundry-Hosted Role Agents

## Objective

Split the Phase 12 monolithic hosted runtime into independent Foundry-hosted
role agents:

```text
maze-analyst-agent
maze-worker-agent-a
maze-worker-agent-b
```

## What Changes

Before Phase 13:

```text
maze-monolithic-agent
  -> Analyst role
  -> Worker Agent A role
  -> Worker Agent B role
  -> in-process coordinator memory
  -> Foundry toolbox MCP Maze Tool
```

After Phase 13:

```text
Coordinator / WebUI boundary
  -> maze-analyst-agent
  -> request-scoped Team Memory
  -> maze-worker-agent-a
  -> maze-worker-agent-b
```

Worker agents still call:

```text
Foundry toolbox MCP -> OpenAPI wrapper -> Azure Function Maze Tool
```

## Why This Matters

This is the first phase where Analyst, Worker A, and Worker B are no longer
just role functions inside one hosted process. Each role has its own hosted-agent
deployment boundary and can be monitored, authorized, scaled, or replaced
independently.

## Shared Memory Boundary

This phase intentionally keeps Team Memory request-scoped. That teaches the
agent split without adding a storage service in the same step.

The next phase should move Team Memory into low-cost Azure durable storage.

## Result Observed

The Azure WebUI now returns `source=foundry-split-role-agents`. The combined
trace shows three hosted role agents, 17 model calls, 32 Foundry toolbox MCP
Maze Tool calls, and zero direct HTTP tool calls.
