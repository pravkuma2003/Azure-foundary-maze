# Phase 14 Validation

## Expected Result

```text
WebUI /api/run returns source=foundry-split-role-agents.
Trace summary reports shared_memory_backend=Azure Blob Storage.
Trace summary includes a team_memory_run_id.
/api/memory?run_id=<id> reads back persisted Team Memory.
Persisted memory includes assignment.maze_a, assignment.maze_b, result.maze_a, and result.maze_b.
```

## Live Result

```text
status: complete
source: foundry-split-role-agents
memory_backend: Azure Blob Storage
team_memory_run_id: phase14-f1e551a00c3e45ac
team_memory_writes: 6
team_memory_reads: 7
llm_calls: 17 / 25
foundry_toolbox_mcp_calls: 32
direct_http_tool_calls: 0
memory_readback_keys: assignment.maze_a, assignment.maze_b, coordination_boundary, mission, result.maze_a, result.maze_b
```

## Generated Artifacts

```text
runs/phase14_azure_durable_team_memory.json
runs/phase14_azure_durable_team_memory_webui.zip
visuals/PHASE14_VISUAL.html
PHASE14_AZURE_DURABLE_TEAM_MEMORY.md
PHASE14_VALIDATION.md
PROGRESS.html
```
