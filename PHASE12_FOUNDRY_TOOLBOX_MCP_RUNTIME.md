# Phase 12 - PydanticAI Runtime Uses Foundry Toolbox MCP

## Objective

Switch the hosted PydanticAI maze runtime from direct HTTP tool calls to the
Foundry toolbox MCP endpoint.

## What Changed

Before:

```text
PydanticAI hosted agent
  -> ExternalMazeToolProgram
  -> Azure Function Maze Tool
```

After:

```text
PydanticAI hosted agent
  -> FoundryToolboxMCPMazeToolProgram
  -> Foundry toolbox MCP endpoint
  -> Foundry OpenAPI wrapper
  -> Azure Function Maze Tool
```

## Why This Matters

Phase 11 made the tool visible in Foundry. Phase 12 makes the runtime consume
that Foundry-managed tool path.

This preserves PydanticAI as the agent framework while using Foundry as the
tool registry, auth holder, and MCP exposure layer.

## Fallback

The runtime still keeps the older direct HTTP path as a fallback if
`MAZE_TOOL_MCP_ENDPOINT` is not configured. The active Azure deployment sets
that variable, so the live WebUI should show `foundry-toolbox-mcp` tool events.
