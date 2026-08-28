# Phase 14 - Azure Durable Team Memory

## Objective

Move Team Memory from request-scoped JSON into durable Azure Blob Storage while
keeping the split Foundry-hosted role agents unchanged.

## What Changed

Before:

```text
Azure WebUI Coordinator
  -> request-local Team Memory dict
  -> maze-analyst-agent
  -> maze-worker-agent-a
  -> maze-worker-agent-b
```

After:

```text
Azure WebUI Coordinator
  -> Azure Blob Storage Team Memory
  -> maze-analyst-agent
  -> maze-worker-agent-a
  -> maze-worker-agent-b
```

## Why This Matters

Independent agents need a shared state boundary that survives a single request.
This phase keeps orchestration simple but makes memory durable and inspectable.

## Cost Posture

The phase reuses the existing Function App storage account and creates only one
Blob container, `team-memory`. No new hosted agents, model deployments,
toolboxes, or storage accounts are created.
