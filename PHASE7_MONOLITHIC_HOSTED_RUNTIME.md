# Phase 7 - Monolithic Foundry-Hosted Maze Runtime

## Objective

Move the local maze application's agent, tool, worker, orchestrator, and memory
logic together into one Foundry-hosted runtime package.

This phase teaches runtime migration, not Azure-native decomposition.

## What Moves Together

```text
Pydantic AI Analyst
Pydantic AI Worker Agent A
Pydantic AI Worker Agent B
deterministic orchestrator
Maze Tool validation
Team Memory / trace state
HTML/result generation
```

## What Does Not Move Yet

```text
Maze Tool is not a separate Foundry tool.
Team Memory is not Azure Storage or Cosmos DB.
Worker agents are not separate hosted agents.
Orchestrator is not an Azure workflow service.
```

## Why This Approach

The goal is to prove that the local app can cross the hosting boundary with
minimal architectural change. Once that works, later phases can split tools,
memory, and workers one at a time.

## Package

```text
hosted/phase7-monolithic-maze-agent
```

The package includes `azure.yaml`, `agent.yaml`, `main.py`, requirements, and a
copy of the public-safe maze runtime source.
