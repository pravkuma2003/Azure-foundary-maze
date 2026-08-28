# Phase 1: Portability Inventory

## Learning Objective

Understand what exists in the local maze app and which parts can move to Azure
without rewriting the core learning program.

## New Concept

Portability boundary.

```text
Portable:
  agent roles
  maze domain
  call-budget accounting
  trace schema
  local tool semantics

Not portable as-is:
  private IP addresses
  local filesystem paths
  local service names
  generated traces with local provider metadata
  generated HTML with embedded local provider metadata
```

## Why This Comes First

Before using Foundry Toolkit or provisioning Azure resources, the local project
needs to be safe to publish and easy to clone on another computer.

## Local to Azure Map

```text
Analyst Agent
  -> Foundry-hosted agent

Worker Agent A / B
  -> Foundry-hosted agents introduced one at a time

Maze Tool
  -> in-process first, then Azure-hosted tool boundary when needed

Team Memory
  -> in-process first, then Azure-native memory/state backend when needed

Trace HTML
  -> Foundry traces plus optional generated review page
```

## Cost Guardrails

```text
Use one Foundry project and one model deployment at first.
Deploy one hosted agent before introducing multiple hosted agents.
Keep traces short and preserve the 25-call learning budget.
Do not add Azure Functions, Cosmos DB, Storage, or extra monitoring services
until a phase explicitly needs that construct.
Clean up lab resources when they are no longer needed.
```

## Deliverable

```text
runs/phase1_inventory.json
visuals/PHASE1_VISUAL.html
PHASE1_VALIDATION.md
```

## Knowledge Check

1. Which files are safe to publish?
2. Which files contain local machine details?
3. Which local constructs should become Azure services?
4. What should remain portable between local and Azure?
5. Why should Azure login happen after the inventory?
