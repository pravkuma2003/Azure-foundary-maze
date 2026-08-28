# Phase 11 - Foundry-Registered Maze Tool

## Objective

Register the external Azure Function Maze Tool as a Foundry-managed OpenAPI
tool through a toolbox and project connection.

## Why This Phase Exists

Phase 10 made the Maze Tool a real external Azure Function. Foundry could not
show it as a Foundry tool because only our Python code knew about the HTTP
endpoint.

Phase 11 adds the Foundry-native registration:

```text
Azure Function Maze Tool
  -> OpenAPI contract
  -> Foundry project connection for x-functions-key
  -> Foundry toolbox
  -> OpenAPI tool inside toolbox
```

## What Should Be Visible In Foundry

Look under the Foundry project Tools area, especially the Toolboxes tab:

```text
Toolbox: maze-toolbox
Tool:    maze_tool_api
Auth:    maze-tool-function-key project connection
```

The individual Azure Function App still appears under Azure resources, not as
an agent by itself.

## Runtime Boundary

The live maze WebUI still uses the Phase 10 runtime path:

```text
PydanticAI hosted agent -> ExternalMazeToolProgram -> Azure Function
```

The next phase can switch the PydanticAI runtime to consume the toolbox MCP
endpoint instead of the direct HTTP client.

## Auth Shape Note

The toolbox file uses the runtime-compatible project connection shape:

```json
{
  "type": "project_connection",
  "security_scheme": {
    "project_connection_id": "maze-tool-function-key"
  }
}
```
