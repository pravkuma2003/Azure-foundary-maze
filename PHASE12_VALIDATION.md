# Phase 12 Validation

## Expected Result

```text
Hosted agent has MAZE_TOOL_MCP_ENDPOINT configured.
Live WebUI /api/run returns source=foundry-hosted-agent.
Trace summary shows foundry_toolbox_mcp_calls > 0.
Trace summary shows direct_http_tool_calls == 0.
Maze tool boundary is FoundryToolboxMCPMazeToolProgram.
```

## Command

```bash
python3 scripts/phase12_foundry_toolbox_mcp_runtime.py --apply
```

## Generated Artifacts

```text
runs/phase12_foundry_toolbox_mcp_runtime.json
visuals/PHASE12_VISUAL.html
PHASE12_FOUNDRY_TOOLBOX_MCP_RUNTIME.md
PHASE12_VALIDATION.md
PROGRESS.html
```
