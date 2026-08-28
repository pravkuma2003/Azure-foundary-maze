# Phase 15 - Monitoring Consolidation

## Objective

Consolidate duplicate monitoring resources while leaving Function App storage
unchanged.

## What Changed

Before:

```text
maze-webui-func-prav-ada483 -> App Insights A -> managed LAW A
maze-tool-func-prav-ada483  -> App Insights B -> managed LAW B
```

After:

```text
maze-webui-func-prav-ada483 -> shared App Insights -> shared managed LAW
maze-tool-func-prav-ada483  -> shared App Insights -> shared managed LAW
```

## What Did Not Change

The WebUI and Maze Tool Function Apps still use their existing storage accounts.
The shared Y1 Consumption App Service plan also remains unchanged.

## Why This Matters

Monitoring is a support boundary, not part of the agent runtime. Consolidating it
reduces duplicate resources without changing agent behavior, tool calls, durable
Team Memory, or Foundry-hosted role agents.
