# Phase 6 - Pydantic AI Analyst Agent on Foundry Model

## Objective

Run the Analyst role locally through Pydantic AI while the model inference runs
against the Azure Foundry deployment.

This phase proves a narrow boundary:

```text
local Pydantic AI agent code
  -> Foundry project endpoint
  -> Foundry model deployment
  -> typed Pydantic output
```

It does not create a Foundry-hosted agent yet.

## What Changed

Phase 5 proved that a small direct adapter can call the Foundry model.

Phase 6 puts Pydantic AI back in the loop:

```text
Analyst Agent v1       local Python process
Pydantic AI            local framework
Foundry model call     Azure-hosted inference
Maze tools             not invoked
Worker agents          not invoked
Team memory            not invoked
```

## Why This Matters

The migration should not jump directly from local code to a fully hosted
multi-agent deployment.

This phase checks whether the existing Pydantic AI role abstraction can keep its
shape while the model backend changes. If this works, later phases can migrate
hosting separately from reasoning behavior.

## Cost Control

The validation makes one short `gpt-4.1-mini` call through Foundry. No new Azure
resources are created.

## Command

```bash
.venv-phase6/bin/python scripts/phase6_foundry_analyst_agent.py
```

