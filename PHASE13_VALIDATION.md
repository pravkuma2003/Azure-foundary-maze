# Phase 13 Validation

## Expected Result

```text
Analyst role validates as an independent role entrypoint.
Worker Agent A validates as an independent role entrypoint.
Worker Agent B validates as an independent role entrypoint.
Each role returns JSON with status=complete.
The hosted deployment path creates three Foundry-hosted agents when --apply is used.
```

## Local Validation

```text
analyst: passed
worker_a: passed
worker_b: passed
```

## Hosted Deployment

```text
maze-analyst-agent: deployed
maze-worker-agent-a: deployed
maze-worker-agent-b: deployed
```

## Live WebUI Validation

```text
Status: passed
source: foundry-split-role-agents
hosted_role_agents: 3
llm_call_budget_used: 17 / 25
foundry_toolbox_mcp_calls: 32
direct_http_tool_calls: 0
```

The WebUI calls the Analyst, Worker Agent A, and Worker Agent B hosted agents,
passes request-scoped Team Memory between them, and renders the combined trace.

## Generated Artifacts

```text
runs/phase13_split_independent_role_agents.json
visuals/PHASE13_VISUAL.html
PHASE13_SPLIT_INDEPENDENT_ROLE_AGENTS.md
PHASE13_VALIDATION.md
PROGRESS.html
```
