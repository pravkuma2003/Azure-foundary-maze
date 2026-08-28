# Phase 10 Validation

## Expected Result

```text
Maze Tool is visible as a separate Azure Function App.
/api/maze/health returns HTTP 200 without a key.
/api/maze/openapi.json returns the OpenAPI contract.
/api/maze/inspect and /api/maze/move require function auth.
Hosted agent receives MAZE_TOOL_BASE_URL and MAZE_TOOL_KEY through environment configuration.
Live WebUI /api/run returns external-http MazeTool events.
```

## Command

```bash
python3 scripts/phase10_external_maze_tool.py --deploy --deploy-hosted-agent --update-webui-sample
```

## Generated Artifacts

```text
tools/phase10-maze-tool-function/
runs/phase10_external_maze_tool.json
runs/phase10_maze_tool_function.zip
runs/phase10_external_tool_sample/
visuals/PHASE10_VISUAL.html
PHASE10_EXTERNAL_MAZE_TOOL.md
PHASE10_VALIDATION.md
PROGRESS.html
```
