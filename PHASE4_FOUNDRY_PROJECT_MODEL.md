# Phase 4: Foundry Project and Model Deployment

## Learning Objective

Create the smallest usable Microsoft Foundry base for the maze migration.

## New Concept

Cloud resource boundary.

```text
Local agent code:
  still unchanged

Azure control plane:
  one resource group
  one Foundry resource
  one Foundry project
  one model deployment
```

## Why This Comes After Phase 3

Phase 3 proves that the personal tenant and subscription are selected. Phase 4
is the first phase that creates Azure resources, so it must stay deliberately
small.

## Resource Plan

```text
Subscription: Visual Studio Enterprise Subscription
Region: eastus
Resource group: rg-maze-foundry-lab
Foundry resource kind: AIServices
Foundry resource SKU: S0
Project: maze-migration-lab
Model deployment: gpt41mini-maze
Model: gpt-4.1-mini
Deployment SKU: GlobalStandard
Deployment capacity: 50
Hosted agents created: 0
Inference calls made: 0
```

## Cost Guardrails

```text
Use one resource group so cleanup is simple.
Use one Foundry resource with project management enabled.
Use one project.
Use one model deployment with enough capacity for smooth manual learning tests.
Do not create hosted agents yet.
Do not create Azure Functions, Cosmos DB, Storage, or custom monitoring yet.
Do not run inference in this phase.
```

## Why gpt-4.1-mini First

`qwen3-32b` is visible in eastus and can be revisited later for model-parity
experiments. Phase 4 uses `gpt-4.1-mini` first because it is a smaller OpenAI
format deployment with Foundry agent support, making it the lowest-risk way to
validate the Azure plumbing before moving agent behavior.

The first deployment attempt used the regional `Standard` SKU and failed because
that quota was zero in the personal subscription. The successful path uses
`GlobalStandard`.

The deployment was later increased from capacity `1` to `50` to avoid repeated
manual lab tests hitting the prior low-throughput rate limit. This changes
allowed throughput, not the number of calls the curriculum code chooses to make.

## Cleanup

If the lab resources should be removed:

```bash
az group delete --name rg-maze-foundry-lab --yes --no-wait
```

## Deliverable

```text
runs/phase4_foundry_project_model.json
visuals/PHASE4_VISUAL.html
PHASE4_VALIDATION.md
```

## Knowledge Check

1. Why do we create only one resource group?
2. Why does the Foundry resource need project management enabled?
3. Why do we deploy a model before creating hosted agents?
4. Why are inference calls still zero in this phase?
5. What is the cleanup boundary for this lab?
